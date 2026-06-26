import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.skills import hippocampus_client as hippo

scheduler = AsyncIOScheduler()


def start_scheduler():
    from src.dao.reminder import get_all_active_reminders
    reminders = get_all_active_reminders()
    for r in reminders:
        _schedule_reminder(r)
    _set_daily_crons()
    scheduler.start()
    logging.info(f"提醒调度器已启动，加载了 {len(reminders)} 条活跃提醒")


def schedule_reminder_by_id(reminder_id: int):
    from src.dao.reminder import get_reminder_by_id
    r = get_reminder_by_id(reminder_id)
    if r and r.is_active:
        _schedule_reminder(r)


def unschedule_reminder(reminder_id: int):
    job_id = f"reminder_{reminder_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def _schedule_reminder(reminder):
    job_id = f"reminder_{reminder.id}"
    if reminder.cron_expression:
        try:
            trigger = CronTrigger.from_crontab(reminder.cron_expression)
        except Exception as e:
            logging.error(f"提醒 {reminder.id} cron 解析失败: {e}")
            return
    else:
        remind_at = reminder.remind_at
        if remind_at and remind_at <= datetime.now():
            logging.info(f"提醒 {reminder.id} 已过期，标记为失效")
            from src.dao.reminder import cancel_active_reminder
            cancel_active_reminder(reminder.id)
            return
        trigger = DateTrigger(run_date=remind_at)

    scheduler.add_job(
        _fire_reminder,
        trigger=trigger,
        args=[reminder.id],
        id=job_id,
        replace_existing=True,
    )


def _set_daily_crons():
    from src.dao.status import load_schedule
    sleep_h, sleep_m, wake_h, wake_m = load_schedule()

    scheduler.add_job(
        _sleep_check,
        CronTrigger(hour=sleep_h, minute=sleep_m),
        id="daily_sleep_check",
        replace_existing=True,
    )
    scheduler.add_job(
        _morning_wake,
        CronTrigger(hour=wake_h, minute=wake_m),
        id="daily_morning_wake",
        replace_existing=True,
    )
    logging.info(f"作息 cron 已设置: 睡觉={sleep_h:02d}:{sleep_m:02d}  起床={wake_h:02d}:{wake_m:02d}")


def _restart_sleep_check_if_needed():
    from src.dao.status import load_schedule
    now = datetime.now()
    sleep_h, _, wake_h, _ = load_schedule()

    if sleep_h > wake_h:
        in_sleep_zone = now.hour >= sleep_h or now.hour < wake_h
    else:
        in_sleep_zone = sleep_h <= now.hour < wake_h

    if in_sleep_zone:
        scheduler.add_job(
            _sleep_check, DateTrigger(now + timedelta(hours=1)),
            id="daily_sleep_check_defer", replace_existing=True,
        )


async def _sleep_check():
    import src.plugins.emaid as emaid
    now = datetime.now()

    # 1. 打游戏/打盹中 → 自动过渡到睡觉中
    if emaid.SLEEP_MODE and emaid.SLEEP_PHASE != "睡觉中":
        old_phase = emaid.SLEEP_PHASE
        emaid.SLEEP_PHASE = "睡觉中"
        emaid._sync_sleep_to_db()
        enter_msg = f"（爱丽丝{old_phase}太久了，该睡觉了~）"
        for llm in emaid.llm_list.values():
            await llm.add_user_message_to_history(enter_msg)
        return

    # 2. 已经在睡觉中 → 跳过
    if emaid.SLEEP_MODE:
        return

    # 3. 有群活跃中 → 推迟 1 小时
    any_busy = any(not emaid.group_locked.get(gid, True) for gid in emaid.llm_list)
    if any_busy:
        scheduler.add_job(
            _sleep_check, DateTrigger(now + timedelta(hours=1)),
            id="daily_sleep_check_defer", replace_existing=True,
        )
        return

    # 4. 找最近 10 分钟内 bot 回复过的群
    best_group = None
    best_time = None
    sessions = await hippo.list_sessions()
    for s in sessions:
        sid = s["session_id"]
        lr = s["last_reply"]
        if best_time is None or lr > best_time:
            best_time = lr
            best_group = sid

    if best_group and (now - best_time).total_seconds() < 600:
        emaid.message_buffer.setdefault(best_group, []).append(
            f"（系统提醒）已经到{now.hour}点了，爱丽丝看看群里的大家都安静了吗？"
            f"如果安静了就去睡觉吧（用 go_to_sleep(rest_type='睡觉中')），"
            f"如果还有人聊天就道个晚安再等等~"
        )
        await emaid._drain_one_group(best_group)
    else:
        emaid.SLEEP_MODE = True
        emaid.SLEEP_PHASE = "睡觉中"
        emaid._sync_sleep_to_db()

    # 5. 没睡 → 1 小时后重试
    if not emaid.SLEEP_MODE:
        scheduler.add_job(
            _sleep_check, DateTrigger(now + timedelta(hours=1)),
            id="daily_sleep_check_defer", replace_existing=True,
        )


async def _morning_wake():
    import src.plugins.emaid as emaid

    if not emaid.SLEEP_MODE:
        return

    emaid.SLEEP_MODE = False
    emaid._sync_sleep_to_db()
    wake_msg = emaid._get_sleep_wake_history()
    if wake_msg:
        for llm in emaid.llm_list.values():
            await llm.add_user_message_to_history(wake_msg)
    await emaid._drain_all_buffered()


async def _fire_reminder(reminder_id: int):
    from src.dao.reminder import get_reminder_by_id, update_reminder_fired, cancel_active_reminder
    import src.plugins.emaid as emaid
    from nonebot import get_bot
    from nonebot.adapters.onebot.v11 import MessageSegment, Message
    from src.dao.status import bot_id
    from src.plugins.emotion import remove_emotion, check_emotion

    reminder = get_reminder_by_id(reminder_id)
    if not reminder or not reminder.is_active:
        return

    was_sleeping = emaid.SLEEP_MODE
    if was_sleeping:
        emaid.SLEEP_MODE = False
        emaid._sync_sleep_to_db()
        wake_msg = emaid._get_sleep_wake_history()
        if wake_msg:
            for llm in emaid.llm_list.values():
                await llm.add_user_message_to_history(wake_msg)

    llm = emaid.getLLM(str(reminder.group_id))
    username = emaid.get_talker_name(str(reminder.user_id))

    prompt = (
        f"（爱丽丝突然想起一件事）之前爱丽丝答应到时间提醒{username}[id={reminder.user_id}]"
        f"关于这件事：\"{reminder.content}\"，现在差不多到时间了。"
        f"爱丽丝快像平时聊天一样，自然地提醒一下他吧~"
    )
    reply = await llm.call_for_reminder(prompt)
    if reply is None:
        logging.error(f"提醒 {reminder.id} LLM 生成失败，跳过")
        return

    emoji_file = check_emotion(str(reminder.user_id), reply)
    clean_reply = remove_emotion(reply)

    try:
        bot = get_bot(bot_id)
        msg = Message()
        if emoji_file:
            msg.append(MessageSegment.image(file=emoji_file))
        msg.append(MessageSegment.at(user_id=int(reminder.user_id)))
        msg.append(MessageSegment.text(f" {clean_reply}"))
        await bot.send_group_msg(group_id=int(reminder.group_id), message=msg)
    except Exception as e:
        logging.error(f"提醒 {reminder.id} 消息发送失败: {e}")

    if reminder.cron_expression:
        trigger = CronTrigger.from_crontab(reminder.cron_expression)
        next_fire = trigger.get_next_fire_time(None, datetime.now())
        update_reminder_fired(reminder.id, next_fire)
    else:
        cancel_active_reminder(reminder.id)
        unschedule_reminder(reminder.id)

    if was_sleeping:
        asyncio.create_task(emaid._drain_all_buffered())
        _restart_sleep_check_if_needed()
