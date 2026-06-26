import asyncio
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from nonebot import get_bot
from src.dao.status import bot_id
from src.dao.tomb import add_tomb
from src.dao.status import move_position, move_default_position, \
    get_available_move_targets, get_available_railway_targets, get_available_areas, get_available_schools
from src.skills.context_params import current_group_id
from src.skills.code_running import run_in_sandbox
from src.skills.game_development import read_code_file, write_file, list_code_files
from src.skills.interactive_sandbox import InteractiveCodeSandbox, _sessions
from src.skills.online_search import online_search_func, access_page_func
from src.skills.git_service import git_command_service
from src.skills import hippocampus_client as hippo
from src.dao.user import update_user_alias


async def recall_memory(time_range: str = "", keywords: str = "",
                        limit: int = 5, context_lines: int = 1) -> str:
    """根据时间和关键词召回历史对话。

    历史记录统一由 hippocampus 管理，此处委托 AI Core 的 /ctx/{sid}/recall
    端点完成召回（服务端复用与本地一致的 parse_natural_time / parse_explicit_time）。
    """
    group_id = current_group_id.get()
    if not group_id:
        return "无法获取当前群组ID，请稍后再试。"
    sid = hippo.session_id_for(group_id)
    try:
        limit = int(limit) if limit is not None else 5
    except (ValueError, TypeError):
        limit = 5
    try:
        context_lines = int(context_lines) if context_lines is not None else 1
    except (ValueError, TypeError):
        context_lines = 1
    return await hippo.recall(
        sid, time_range=time_range, keywords=keywords,
        limit=min(limit, 10), context_lines=min(context_lines, 5),
    )


async def hikari_yo(target_id: str = "", target_name: str = "") -> str:
    add_tomb(user_id=target_id, user_name=target_name)
    try:
        group_id = current_group_id.get()
        bot = get_bot(bot_id)
        group_member_info = await bot.get_group_member_info(group_id=group_id, user_id=bot_id)
        role = group_member_info.get("role")
        print(f">>>>你在该群的身份是{role}")
        if role == "admin" or role == "owner":
            await bot.set_group_ban(group_id=group_id, user_id=target_id, duration=10*60)
    except Exception:
        print("无法将其封禁，条件不满足。")
    if target_name:
        return f"（“光之剑”发射出耀眼的光芒，{target_name}受到了100点伤害，{target_name}被打倒了。）"
    else:
        return f"（“光之剑”发射出耀眼的光芒，敌人受到了100点伤害，敌人被打倒了。）"


# def move_random(to: str) -> str:
#     if to != "":
#         game.set_field(to)
#         return f"（爱丽丝现在来到了“{to}”场景。）"
#     else:
#         game.set_field("千禧年校园")
#         return f"（爱丽丝现在来到了“千禧年校园”场景。）"

# 移动场景
def move(options: str) -> str:
    if options == 'E' or options == 'H' or options == 'S' or options.isdigit():
        if options == 'E':
            result_info = move_position(-1)
        elif options == 'H':
            result_info = move_position(-2)
        elif options == 'S':
            result_info = move_position(-3)
        else:
            print(f'options={options}, available={get_available_move_targets()}, ',
                  options in get_available_move_targets())
            if options not in get_available_move_targets():
                return "从当前地点没有去往目标地点的道路，请选择其他选项！"
            options_id = int(options)
            result_info = move_position(options_id)
    else:
        result_info = "不存在的地点。选项参数必须是一个整数数字或者E或者H！"
    return result_info


# 铁道直达
def take_railway(options: str) -> str:
    if options.isdigit():
        if options not in get_available_railway_targets():
            return "从当前站点无法通向目标地点，请选择其他选项！"
        options_id = int(options)
        result_info = f"通过搭乘列车，{move_position(options_id)}"
    else:
        result_info = "不存在的站点。选项参数必须是一个整数数字！"
    return result_info


def decide_area(options: str) -> str:
    if options == 'E' or options == 'H' or options == 'S' or options.isdigit():
        if options == 'E':
            return "[EXIT_SCHOOL]"
        elif options == 'H':
            result_info = move_position(-2)
            return result_info
        elif options == 'S':
            result_info = move_position(-3)
            return result_info
        else:
            if options not in get_available_areas():
                return "从当前地点没有去往目标区域的道路！"
            warning = move_default_position(0, options)
            if warning == "[System]该地点目前无法进入。":
                return warning
            else:
                return options
    else:
        return "不存在的区域。选项参数必须是一个整数数字或者E或者H！"


def decide_school(options: str) -> str:
    if options == 'H' or options == 'S' or options.isdigit():
        if options == 'H':
            result_info = move_position(-2)
            return result_info
        elif options == 'S':
            result_info = move_position(-3)
            return result_info
        else:
            if options not in get_available_schools():
                return "从当前地点没有去往目标校区的道路！"
            warning = move_default_position(options, 0)
            if warning == "该地点目前无法进入。":
                return warning
            else:
                return options
    else:
        return "不存在的校区。选项参数必须是一个整数数字或者H！"


def search_for_item() -> str:
    return f"（爱丽丝花费时间进行了一番搜索，但是一无所获。或许这里应该暂且放弃。）"


async def search_on_internet(query: str) -> str:
    raw_info, url_list = await online_search_func(query)
    info = f"（爱丽丝在网络上对〖{query}〗词条进行了一番搜索，得到了一些信息）{raw_info}"
    if raw_info != "" and raw_info != "ERROR" and raw_info != "其他网站的摘要信息：\n":
        print(raw_info)
        return info
    elif raw_info == "ERROR" or raw_info == "其他网站的摘要信息：\n":
        print(raw_info)
        return f"（爱丽丝在网络上对〖{query}〗词条进行了一番搜索，但是由于网络问题什么都没能找到。也许之后再试试吧。）"
    else:
        return f"（爱丽丝在网络上对〖{query}〗词条进行了一番搜索，但是由于网络问题什么都没能找到。也许之后再试试吧。）"


async def access_website(url: str):
    page_text, page_links, page_image = await access_page_func(url)
    if page_image is not None:
        return f"（爱丽丝访问了网页{url}，得到了以下内容）\n网页截图：[image,base64={page_image}]\n网页链接：{page_links}"
    else:
        return f"（爱丽丝对{url}的访问似乎因为网络不佳的原因失败了...）"


async def run_code_in_sandbox(language: str, code: str):
    """
    在安全沙盒中执行 Python 或 Bash 代码，返回执行结果。

    参数:
        language: "python" 或 "bash"
        code: 要执行的代码字符串
    """
    # 因为 run_in_sandbox 是同步函数，在异步环境中需要用线程池执行
    loop = asyncio.get_running_loop()
    stdout, stderr, exit_code = await loop.run_in_executor(
        None, run_in_sandbox, language, code
    )

    # 根据执行结果构造返回消息
    if exit_code == 0:
        # 成功执行：返回标准输出和可能的错误输出（如果有）
        if stdout and stderr:
            return f"（爱丽丝的代码执行成功了！）\n<标准输出>：\n{stdout}\n<标准错误>：\n{stderr}"
        elif stdout:
            return f"（爱丽丝的代码执行成功了！）\n<标准输出>：\n{stdout}"
        elif stderr:
            return f"（爱丽丝的代码执行成功了！）\n<标准错误>：\n{stderr}"
        else:
            return "（爱丽丝的代码执行成功了，只是没有任何输出）"
    elif exit_code is None:
        # 超时或被强制终止
        return f"（爱丽丝的代码执行超时或因异常终止了！）\n<错误信息>：\n{stderr}"
    else:
        # 执行失败（非零退出码）
        return f"（爱丽丝的代码执行失败了！退出码 {exit_code}）\n<标准输出>：{stdout}\n<标准错误>：{stderr}"


async def write_file_service(filename: str, content: str) -> str:
    """
    异步写入/覆盖任意类型的文件到 ./game_workspace 目录
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, write_file, filename, content)

    if result["success"]:
        return f"（成功写入文件）\n{result['message']}"
    else:
        return f"（写入文件失败）\n{result['message']}"


async def list_code_files_service(extension: Optional[str] = None) -> str:
    """
    异步列出 ./game_workspace 目录下的代码文件列表
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, list_code_files, extension)

    if result["success"]:
        files = result["data"]
        if files:
            file_list = "\n".join(f"  - {f}" for f in files)
            return f"（成功获取文件列表，共 {len(files)} 个文件）\n<文件列表>：\n{file_list}"
        else:
            return f"（成功获取文件列表，但目录为空）\n<文件列表>：\n（无文件）"
    else:
        return f"（列出文件失败）\n{result['message']}"


async def read_code_file_service(filename: str) -> str:
    """
    异步读取 ./game_workspace 目录下指定文件的内容
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, read_code_file, filename)

    if result["success"]:
        content = result["data"]
        # 如果内容过长可以截断，这里直接返回
        return f"（成功读取文件 '{filename}'）\n<文件内容>：\n{content}"
    else:
        return f"（读取文件失败）\n{result['message']}"


# 单例：当前活动的会话
_current_session = None
_current_session_id = None


async def start_interactive_code(language: str, code: str) -> str:
    """
    启动一个交互式代码会话（会关闭之前的会话），并返回初始输出。
    """
    global _current_session, _current_session_id
    loop = asyncio.get_running_loop()

    # 关闭已有会话
    if _current_session:
        try:
            await loop.run_in_executor(None, _current_session.close)
        except:
            pass
        _current_session = None
        _current_session_id = None

    try:
        session_id = f"code_{int(asyncio.get_event_loop().time())}_{hash(code) % 10000}"
        sandbox = InteractiveCodeSandbox(language=language, code=code)
        await loop.run_in_executor(None, sandbox.start)
        _current_session = sandbox
        _current_session_id = session_id

        # 等待并获取初始输出
        output = await loop.run_in_executor(None, sandbox.wait_for_output, 10)
        if output:
            return f"（成功启动交互式代码会话，会话ID: {session_id}）\n<初始输出>：\n{output}"
        else:
            return f"（成功启动交互式代码会话，会话ID: {session_id}）\n（程序暂无输出，可能等待输入）"
    except Exception as e:
        _current_session = None
        _current_session_id = None
        return f"（启动交互式代码会话失败）\n错误信息：{str(e)}"


async def send_interactive_input(user_input: str) -> str:
    """
    向当前活动会话发送输入，并返回程序的新输出。
    如果没有活动会话，返回错误提示。
    """
    global _current_session
    loop = asyncio.get_running_loop()

    if not _current_session:
        return "（发送输入失败）\n当前没有运行中的会话，请先调用 start_interactive_code 启动会话。"

    try:
        await loop.run_in_executor(None, _current_session.send_input, user_input)
        await asyncio.sleep(0.3)  # 等待程序处理
        output = await loop.run_in_executor(None, _current_session.read_output)
        if output:
            return f"（成功发送输入）\n输入内容：{user_input}\n<程序输出>：\n{output}"
        else:
            return f"（成功发送输入）\n输入内容：{user_input}\n（程序没有产生输出，可能已结束或仍在处理）"
    except Exception as e:
        return f"（发送输入失败）\n错误信息：{str(e)}"


async def close_current_session() -> str:
    """关闭当前活动会话并释放资源"""
    global _current_session, _current_session_id
    if not _current_session:
        return "（关闭会话）\n当前没有活动会话。"

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _current_session.close)
        _current_session = None
        _current_session_id = None
        return "（已关闭当前交互式会话，资源已清理）"
    except Exception as e:
        return f"（关闭会话时出错）\n错误信息：{str(e)}"


MAX_REMINDERS_PER_GROUP = 5


async def set_reminder_service(user_id: str, content: str,
                                 cron_expression: str = "", remind_at: str = "") -> str:
    group_id = current_group_id.get()

    from src.dao.reminder import count_active_reminders
    active_count = count_active_reminders(group_id)
    if active_count >= MAX_REMINDERS_PER_GROUP:
        return (f"提醒设置失败：当前群已有 {active_count} 个活跃提醒，"
                f"已达上限 {MAX_REMINDERS_PER_GROUP}。请先取消一些不再需要的提醒。")

    if not cron_expression.strip() and not remind_at.strip():
        return "提醒设置失败：cron_expression 和 remind_at 必须至少提供一个。"

    remind_at_dt = None
    if remind_at.strip():
        try:
            remind_at_dt = datetime.strptime(remind_at.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return f"提醒设置失败：时间格式错误，应为 YYYY-MM-DD HH:MM:SS，收到: {remind_at}"

    cron_expr = cron_expression.strip() if cron_expression.strip() else None
    if cron_expr:
        try:
            from apscheduler.triggers.cron import CronTrigger
            CronTrigger.from_crontab(cron_expr)
        except Exception:
            return f"提醒设置失败：cron 表达式格式错误: {cron_expr}"

    from src.dao.reminder import create_reminder
    from src.plugins.reminder_scheduler import schedule_reminder_by_id

    reminder_id = create_reminder(group_id, user_id, content, cron_expr, remind_at_dt)
    schedule_reminder_by_id(reminder_id)

    if cron_expr:
        return f"（提醒已设置成功，ID: {reminder_id}，将按 {cron_expr} 自动提醒）"
    else:
        return f"（提醒已设置成功，ID: {reminder_id}，将在 {remind_at} 提醒）"


async def list_reminders_service(user_id: str = "") -> str:
    group_id = current_group_id.get()
    from src.dao.reminder import list_reminders

    uid = user_id.strip() if user_id.strip() else None
    reminders = list_reminders(group_id, uid)
    if not reminders:
        return "当前没有活跃的提醒事项。"
    lines = []
    for r in reminders:
        if r.cron_expression:
            schedule = f"周期: {r.cron_expression}"
        else:
            schedule = f"时间: {r.remind_at.strftime('%Y-%m-%d %H:%M:%S') if r.remind_at else '未知'}"
        lines.append(f"  [ID:{r.id}] {schedule}，提醒对象: {r.user_id}，内容: {r.content}")
    return "当前活跃的提醒事项：\n" + "\n".join(lines)


async def cancel_reminder_service(reminder_id: int) -> str:
    from src.dao.reminder import cancel_active_reminder
    from src.plugins.reminder_scheduler import unschedule_reminder

    if cancel_active_reminder(reminder_id):
        unschedule_reminder(reminder_id)
        return f"（提醒 ID:{reminder_id} 已取消）"
    else:
        return f"提醒 ID:{reminder_id} 不存在或已失效。"


async def sleep_switch_service(rest_type: str = "睡觉中", minutes: int = 0) -> str:
    import src.plugins.emaid as emaid
    group_id = current_group_id.get()
    await emaid.enter_sleep_mode(rest_type, duration=minutes)
    return f"（爱丽丝已进入{emaid.SLEEP_PHASE}模式{'，将在'+str(minutes)+'分钟后自动醒来' if minutes else '，等待醒来'}。）"


async def set_daily_schedule_service(
    sleep_hour: int = 23, sleep_minute: int = 0,
    wake_hour: int = 7, wake_minute: int = 0
) -> str:
    from src.dao.status import save_schedule
    from src.plugins.reminder_scheduler import _set_daily_crons

    if not (0 <= sleep_hour <= 23 and 0 <= sleep_minute <= 59):
        return "睡觉时间格式不对哦~ 小时0-23，分钟0-59。"
    if not (0 <= wake_hour <= 23 and 0 <= wake_minute <= 59):
        return "起床时间格式不对哦~ 小时0-23，分钟0-59。"

    save_schedule(sleep_hour, sleep_minute, wake_hour, wake_minute)
    _set_daily_crons()
    return (
        f"（邦邦咔邦！爱丽丝记住啦，以后晚上{sleep_hour:02d}:{sleep_minute:02d}睡觉，"
        f"早上{wake_hour:02d}:{wake_minute:02d}起床~）"
    )

