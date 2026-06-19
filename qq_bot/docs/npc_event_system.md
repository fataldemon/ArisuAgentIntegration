# NPC 互动事件系统 - 实施方案

## 总体架构

```
每天凌晨 cron → NPC分布图(t_npc_daily)
    ↓
AI移动到新位置 → 查NPC → build_status显示
    ↓
AI调 random_event → 查看该area所有hotspot
    ↓
AI移动到hotspot → backend type=2 → 生成互动场景+物品 → EXP
```

---

## Phase 1: 数据库基础

### 新建 `src/dao/npc.py`

| 表 | 关键列 | 说明 |
|----|--------|------|
| `Npc` | npc_id(PK), npc_name, department, school_id, appearance, personality, speech_style, relationship, common_activities | NPC 定义（手动录入） |
| `NpcSpawn` | id(PK), npc_id, position_id, weight(0-100), time_period(day/night/all) | 每个NPC在各位置的刷新权重 |
| `NpcDaily` | id(PK), position_id, npc_id, date, is_encountered, slot | 每天凌晨cron生成的NPC分布 |
| `ItemTemplate` | item_id(PK), name, description, type(消耗品/装备/贵重品), effect_hp, effect_exp, effect_attack, effect_defense | 物品模板（AI生成时自动写入） |
| `Inventory` | id(PK), item_template_id, quantity | 爱丽丝的背包 |
| `NpcInteractionLog` | id(PK), npc_id, position_id, event_text, exp_reward, created_at | 所有互动历史（不限日期），供后续互动参考 |

### 修改 `src/dao/map.py`

| 表 | 关键列 | 说明 |
|----|--------|------|
| `PositionEvent` | event_id(PK), position_id, npc_id, event_text, item_name, item_desc, item_type, item_effects(JSON), exp_reward, date, is_triggered | 已触发过的事件记录 |

### 修改 `src/dao/status.py`

EXP 公式两处改为 `level * level * 100`（`get_status_description` 有/无 profession 分支）。

新增函数：

```python
def add_exp(amount: int) -> tuple[int, str]:  # 返回(level_ups, msg)
    """加经验，自动判断升级。升级时补满HP"""
def add_item(item_template_id: int, qty: int = 1):
    """添加物品到背包。如已存在则叠加"""
def use_item(inventory_id: int) -> str:
    """使用物品，根据ItemTemplate.effect_*处理效果，返回结果文本"""
def get_inventory() -> list:
    """返回背包物品列表（带名称和数量）"""
```

**种子数据**（手动录入）：

```sql
-- t_npc: 每个 school 至少 3 个 NPC，需包含外貌/性格/说话/关系/日常
-- t_npc_spawn: 每个 NPC 至少覆盖 2-3 个 position，weight 按亲密程度设定
-- t_item_template: 至少 10 个种子物品（为AI生成提供参考）
```

---

## Phase 2: NPC 每日分布

### 修改 `src/plugins/reminder_scheduler.py`

```python
# startup 注册凌晨 cron
scheduler.add_job(_generate_npc_distribution, CronTrigger(hour=0, minute=0))
```

### 新增 `src/dao/npc.py::generate_daily_distribution()`

```python
def generate_daily_distribution():
    """遍历 t_npc_spawn → 按weight加权随机分配到具体position+slot → INSERT t_npc_daily"""

def get_npcs_at_position(position_id: int, date: str) -> list:
    """查该位置今天有哪些NPC"""

def get_area_hotspots(area_id: int, school_id: int, date: str) -> list:
    """查该area/school内所有有NPC的position列表"""
```

**`size` 使用**：

```python
max_slots = min(size, 3)  # size=1 → 1个格子, size=4 → 3个格子, size=100 → 3个格子
```

分 `day`(6:00-18:00) 和 `night`(18:00-6:00) 两批生成，`time_period='all'` 的 NPC 两批都参与。

---

## Phase 3: 事件生成（backend type=2）

### 修改 `src/plugins/qwenOpenapi.py`

```python
async def call_assistant_for_event(self, npc_data: dict, position_name: str, 
                                    position_desc: str, school_name: str,
                                    recent_interactions: list = None) -> dict:
    """调 backend assistant type=2"""
```

**请求 JSON**：

```json
{
    "type": 2,
    "model": "gpt-3.5-turbo",
    "temperature": 0.8,
    "top_p": 0.95,
    "stream": false,
    "enable_thinking": false,
    "npc": {
        "name": "才羽桃井",
        "appearance": "粉色长发扎成双马尾，戴圆框眼镜...",
        "personality": "乐观开朗，遇事容易激动...",
        "speech_style": "语气活泼爱用感叹号，说话经常蹦出游戏术语",
        "relationship": "游戏开发部的伙伴，负责程序。把爱丽丝当妹妹看待",
        "common_activities": "写代码、玩复古RPG。遇到bug会崩溃，修好后又得意洋洋"
    },
    "recent_interactions": [
        "昨天在游戏开发部活动室一起测试了新写的小游戏",
        "前天桃井送了爱丽丝一罐弹珠汽水"
    ],
    "position_name": "游戏开发部活动室",
    "position_desc": "游戏开发部的社团活动室，这里是爱丽丝的家。",
    "school_name": "千禧年科技学院"
}
```

**后端 prompt 模板**（`llm/chat.py` type=2 分支）：

```
请用《碧蓝档案》的爱丽丝（第一人称视角）写一段今天在{position_name}遇到{npc.name}的互动场景。

〖{npc.name}的人物卡〗
外貌：{appearance}
性格：{personality}
说话风格：{speech_style}
与爱丽丝的关系：{relationship}
日常行为：{common_activities}

〖场景〗{position_desc}

{如果有recent_interactions}
爱丽丝和{npc.name}最近的互动：
{recent_interactions}

要求：
- 80字左右
- 用爱丽丝的语气，括号内描述动作和想法
- 约70%概率只聊天互动，约30%概率NPC送爱丽丝一件小物品

如果NPC送了物品，在场景最后另起一行按格式输出（不要用任何引号包裹）：
物品:名称|描述:简短说明|类型:消耗品/贵重品|效果:hp+数值(多值用逗号分隔)

示例：
（爱丽丝在游戏开发部活动室见到了桃井前辈！桃井前辈推了推眼镜说）"爱丽丝！新写的存档系统跑通啦！给，这个暖手贴~"
物品:像素暖手贴|描述:印着小像素爱心的贴片|类型:消耗品|效果:hp+15
```

**响应格式**：

```json
{
    "scene": "场景文本",
    "item": {
        "name": "像素暖手贴",
        "description": "印着小像素爱心的贴片",
        "type": "消耗品",
        "effects": {"hp": 15}
    }
}
```

或 `item: null`。

---

## Phase 4: 互动流程

### 修改 `src/plugins/emaid.py`

**A. move hook**（`handle_llm_conversation`）：

```python
if function == "move" and 移动到了新位置:
    npcs = get_npcs_at_position(new_pos_id, today)
    # NPC信息由build_status注入，不在此处阻塞
```

**B. `build_status()` 注入**：

查当前位置 `t_npc_daily` → 如果有未 encounter 的 NPC → 注一行：

```
爱丽丝注意到游戏开发部活动室里好像有人在！（是桃井前辈和小绿前辈）
```

如果是已经 encounter 过的 NPC，不重复提示。

**C. `random_event` 函数**（functions/services/function_call）：

```python
func_random_event = {
    'name': 'random_event',
    'description': '看看爱丽丝当前所在的区域附近有没有同学在！可能会触发有趣的互动~',
    'parameters': {'type': 'object', 'properties': {}, 'required': []},
}
```

**Service 返回**（未到达 NPC 位置时）：

```
（附近好像有同学在！）
在〖游戏开发部活动室〗看到了桃井前辈！[感叹号]
在〖图书馆〗注意到了优香同学的身影！[感叹号]
（移动到这些地点后再次使用 random_event 可以和她们互动哦~）
```

**D. 触发互动**（到达 NPC 位置后调 `random_event`）：

```python
# 查 t_position_event 今天是否已生成
event = get_today_event(position_id, npc_id)
if not event:
    # 调 backend type=2
    npc = get_npc(npc_id)
    recent = get_recent_interactions(npc_id, limit=3)
    result = await call_assistant_for_event(npc, position_name, position_desc, school_name, recent_interactions=recent)
    # 保存到 t_position_event + t_npc_interaction_log
    event = save_position_event(position_id, npc_id, result, today)
    save_interaction_log(npc_id, position_id, result['scene'], exp_reward)
    # 处理物品（如果有）
    if result.get('item'):
        item_id = save_item_template(result['item'])
        add_item(item_id, 1)
    # 计算EXP奖励（5-30之间随机）
    exp_reward = random.randint(5, 30)
    add_exp(exp_reward)

# 标记 encountered
mark_npc_encountered(position_id, npc_id, today)

# 返回场景文本给AI（作为observation）
```

返回示例（AI 的 observation）：
```
（爱丽丝在游戏开发部活动室见到了桃井前辈！桃井前辈推了推眼镜说）"爱丽丝！新写的存档系统跑通啦！给，这个暖手贴~"

爱丽丝获得了「像素暖手贴」！（消耗品类，效果: hp+15）
爱丽丝获得了20点经验值~
```

---

## Phase 5: 物品使用系统

### 修改 `src/dao/status.py`

```python
def use_item(inventory_id) -> str:
    # 1. 查 Inventory + ItemTemplate
    # 2. 根据 effect_hp/effect_exp/... 更新 Status
    # 3. quantity -= 1，quantity==0 则删除记录
    # 4. 返回效果描述
```

### AI 工具（functions/services/function_call）

| 函数 | 说明 |
|------|------|
| `check_inventory` | 返回背包物品列表（名称 × 数量 + 描述 + 效果） |
| `use_item` | `use_item(inventory_id)` → 使用指定物品，返回效果文本 |

---

## 改动总览

| Phase | 文件 | 操作 |
|-------|------|------|
| 1 | `src/dao/npc.py` | **新建**：Npc/NpcSpawn/NpcDaily/ItemTemplate/Inventory 表 + CRUD |
| 1 | `src/dao/map.py` | 加 PositionEvent 表 + CRUD |
| 1 | `src/dao/status.py` | 改 EXP 公式为 level²×100 + add_exp/add_item/use_item/get_inventory |
| 2 | `src/dao/npc.py` | generate_daily_distribution/get_npcs_at_position/get_area_hotspots |
| 2 | `src/plugins/reminder_scheduler.py` | 加凌晨 cron → generate_daily_distribution |
| 3 | `src/plugins/qwenOpenapi.py` | call_assistant_for_event() |
| 3 | 后端 `models/base.py` + `llm/chat.py` | type=2 分支：事件+物品生成 |
| 4 | `src/plugins/emaid.py` | move hook、build_status NPC注入、random_event 处理逻辑 |
| 5 | `src/function/functions.py` | func_random_event、func_check_inventory、func_use_item |
| 5 | `src/function/services.py` | 对应 service 实现 |
| 5 | `src/function/function_call.py` | 注册 handler |
| - | **种子数据** | 手动录入 t_npc + t_npc_spawn + t_item_template |
