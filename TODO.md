# TODO：上下文管理 + 工具调用统一化

## 目标

将 QQ Bot 中的**上下文管理**和**工具调用**模块提取为 AI Core 的公共模块。所有渠道（QQ Bot、Bilibili、Unity、Chat 页面）共享同一套上下文管理和工具系统。

## 核心原则

1. **API 端点暂时不变** — 不新增 `/v2/chat` 等新端点，现有 `/v1/chat/completions` 和 `/assistant/v1/chat/completions` 保持不变
2. **QQ Bot 主动调取公共模块** — 不是 AI Core 全权处理，而是 QQ Bot 从自己这边调用公共模块的接口，然后再和原来一样发 API 请求。处理流程和原来区别不大，改动可控
3. **公共数据库** — `t_chat_history` 已在共享数据库 `db/tendou_arisu.db` 中，是上下文管理的基础
4. **分阶段实施** — 逐步迁移，每个阶段可独立测试验证

---

## Phase 1：上下文管理模块提取

**目标**：将 QQ Bot 的 `qwenOpenapi.py`（Qwen 类）中的上下文管理逻辑提取为独立的公共模块，放在项目公共位置（如 `shared/` 或 `ai_core/context/`）。

### 需要提取的功能（从 Qwen 类和 emaid.py）

| 功能 | 当前位置 | 说明 |
|------|---------|------|
| **会话历史管理** | `Qwen.history` | per-session（当前是 per-group）历史列表 |
| **历史持久化** | `chat_history.py` `save_chat_record()` / `load_recent_history()` | 读写 `t_chat_history` 表 |
| **历史截断+摘要** | `Qwen.conclude_summary()` / `shorten_history()` | 超过 `max_history` 时压缩旧消息为摘要 |
| **时间标注** | `Qwen.call()` 中的时间差计算 | 距上次消息 >10分钟插入"（X分钟过去了。）"，>12小时重置历史 |
| **消息缓冲** | `emaid.py` `message_buffer[group_id]` | 快速连续消息合并为一次 LLM 调用 |
| **分组锁** | `emaid.py` `group_locked[group_id]` | 防止同一会话并发 LLM 调用 |
| **Embedding buffer** | `Qwen.embedding_buffer` | 追踪已引用的知识库条目索引 |
| **数据集采集** | `dataset_collection.py` | 记录对话为训练数据 JSONL |
| **状态注入** | `emaid.py` `build_status()` | 构建包含时间、日期、游戏状态的 status 字符串 |
| **FTS5 全文搜索初始化** | `emaid.py` `init_fts()` | 创建 `t_chat_history_fts` 虚拟表 |

### Session 设计

- **Session ID**：自由定义，由渠道自行 format（如 `qq_group_12345`、`bilibili_live`、`chat_user_abc`）
- **只要不重复就行**
- **per-session 状态**：history、embedding_buffer、summary、last_reply_time、processing_lock

### 公共模块接口设计（草案）

```python
class ContextManager:
    def get_session(session_id: str) -> Session
    def save_message(session_id, role, content, thought=None, action=None)
    def load_history(session_id, max_messages=40) -> List[Message]
    def truncate_history(session_id, max_history) -> str  # 返回摘要
    def build_time_annotation(session_id) -> Optional[str]  # "（X分钟过去了。）"
    def recall_memory(session_id, time_range, keywords, ...) -> List[Message]
    def init_fts()  # FTS5 初始化
```

---

## Phase 2：通用工具迁移

**目标**：将 QQ Bot 的 14 个通用工具提取为 AI Core 的 Built-in Functions，在服务端统一执行。

### 工具清单

| # | 工具 | 参数 | 依赖 | 迁移难度 |
|---|------|------|------|---------|
| 1 | `search_on_internet` | query | Chrome/Playwright CDP (port 9222) | 中 |
| 2 | `access_website` | url | Chrome/Playwright CDP | 中 |
| 3 | `run_code_in_sandbox` | language, code | Docker (python:3.11-slim) | 中 |
| 4 | `start_interactive_code` | language, code | Docker + persistent session | 高 |
| 5 | `send_interactive_input` | user_input | Docker active session | 高 |
| 6 | `close_current_session` | (none) | Docker active session | 低 |
| 7 | `write_file` | filename, content | 文件系统 /game_workspace | 低 |
| 8 | `list_code_files` | extension (optional) | 文件系统 | 低 |
| 9 | `read_code_file` | filename | 文件系统 | 低 |
| 10 | `git_command` | git_command | Git CLI + /game_workspace | 低 |
| 11 | `recall_memory` | time_range, keywords, limit, context_lines | SQLite FTS5 (t_chat_history_fts) | 中（需要 session_id） |
| 12 | `set_reminder` | user_id, content, cron/remind_at | SQLite (t_reminder) + APScheduler | 高（需要渠道回调） |
| 13 | `list_reminders` | user_id (optional) | SQLite | 低 |
| 14 | `cancel_reminder` | reminder_id | SQLite + APScheduler | 低 |

### Built-in Function 注册机制

```python
# ai_core/tools/registry.py
class ToolRegistry:
    def register(name, schema, handler)
    def list_tools() -> List[ToolDef]
    def call_tool(name, arguments) -> str

# 执行循环中的路由
if name in mcp_names:       -> MCP 执行（已有）
elif name in builtin_names:  -> Built-in 执行（新增）
else:                        -> 透传给渠道客户端（已有）
```

### 依赖处理

| 依赖 | 当前位置 | 迁移方案 |
|------|---------|---------|
| **Chrome/Playwright** | QQ Bot 进程中启动 | 迁移到 AI Core 进程，或作为独立服务 |
| **Docker** | QQ Bot 进程中调用 | 迁移到 AI Core 进程（需确认 AI Core 进程能访问 Docker） |
| **SQLite FTS5** | QQ Bot 的 `init_fts()` | 迁移到 AI Core 启动时初始化 |
| **APScheduler** | QQ Bot 进程中运行 | 迁移到 AI Core 进程（提醒触发需要回调渠道） |
| **文件系统** | QQ Bot 的 /game_workspace | 迁移到共享路径或 AI Core 管理 |
| **Git CLI** | QQ Bot 调用 subprocess | AI Core 进程同样可调用 |

---

## Phase 3：游戏世界工具迁移

**目标**：将 7 个游戏世界工具迁移到 AI Core。

### 工具清单

| # | 工具 | 参数 | 数据库表 | 特殊逻辑 |
|---|------|------|---------|---------|
| 1 | `move` | options (位置ID/E/H/S) | t_status, t_position | 多步导航状态机的一部分 |
| 2 | `decide_area` | options | t_area, t_status | 返回 [EXIT_AREA]/[EXIT_SCHOOL]/area_id |
| 3 | `decide_school` | options | t_school, t_status | 返回 school_id |
| 4 | `take_railway` | options | t_position (station=1) | 火车站间移动 |
| 5 | `update_alias` | user_id, alias_name | t_user | 设置用户昵称 |
| 6 | `go_to_sleep` | rest_type, minutes | t_status | 进入睡眠/游戏模式，可选自动唤醒 |
| 7 | `set_daily_schedule` | sleep_h/m, wake_h/m | t_status | 更新每日睡眠/唤醒时间表 |

### 导航状态机（关键逻辑）

QQ Bot 的 `emaid.py` 中有一个 `steps` 状态变量控制三级导航：

```
steps=0: 正常移动（move 工具，选择同区域地点）
         | 选择 E（退出区域）
steps=1: 选择区域（decide_area 工具）
         | 选择 E（退出学校）
steps=2: 选择学校（decide_school 工具）
         | 选择学校后
steps=1: 回到选择区域
         | 选择区域后
steps=0: 回到正常移动
```

每一步会**动态切换可用工具列表**：`move_tool(steps, school_id, area_id)` 返回不同的工具定义。

**迁移方案**：将 `steps` 状态纳入 session 或 tool engine 的状态管理。

### 游戏世界状态（需要迁移的内存状态）

QQ Bot 的 `status.py` 中有全局变量追踪可用目标：

```python
available_move_targets = []
available_anchor_targets = []
available_area_targets = []
available_school_targets = []
available_functions = ""
```

这些在 `move_position()` / `find_route()` 调用后更新，并在 `get_general_tools()` 中用于动态填充工具参数的 `{OPTIONS}` 占位符。

**迁移方案**：纳入 AI Core 的游戏世界管理模块。

---

## Phase 4：QQ 专属工具 + 渠道回调

### sword_of_light（光之剑）

唯一需要 QQ API 的工具：
- 写入 `t_tomb`（墓地表）— 可在 AI Core 执行
- 调用 `bot.get_group_member_info()` 判断身份 — 需要 QQ API
- 调用 `bot.set_group_ban()` 禁言 — 需要 QQ API

**方案**：AI Core 执行数据库操作，通过**渠道回调**通知 QQ Bot 执行禁言。

### 渠道回调机制设计

```
AI Core 执行工具 -> 产生渠道动作指令
  |
  v
通过回调通知渠道执行特定动作：
  - 禁言用户
  - 发送图片/表情
  - 发送语音
  - 发送合并转发消息

渠道注册时提供回调接口（后续设计）
```

### 未来目标

**消息发送/接收也作为 tool call**：让 AI 通过 tool call 主动发送消息到渠道，而不是被动响应。这样 AI 可以：
- 主动发起对话
- 在工具执行过程中发送中间状态（如"正在搜索..."）
- 同时向多个渠道发送消息

---

## Phase 5：QQ Bot 瘦身

工具和上下文管理迁移完成后，QQ Bot 简化为：

```
QQ Bot（薄桥接层）
├── NoneBot2 消息接收
├── 消息格式化（用户名、图片、@、回复链）
├── 调用公共模块：
│   ├── ContextManager.get_session(session_id)
│   ├── ContextManager.save_message(...)
│   └── 构建请求 -> POST /v1/chat/completions
├── 响应处理：
│   ├── 情绪标记 -> emoji 图片
│   ├── CQ 码 -> QQ @ 消息
│   ├── 长消息分段发送
│   └── 语音合成（可选）
├── 渠道回调接口（接收 AI Core 的动作指令）
└── 睡眠模式管理（可能也迁到 AI Core）
```

**保留在 QQ Bot 中的功能**：
- NoneBot2 框架 + OneBot V11 适配器
- QQ 消息格式化（CQ 码解析、图片处理）
- 表情映射（emotion.py）
- 语音合成（voice.py）
- 消息分段发送（_send_response）

**迁移到公共模块的功能**：
- 对话历史管理（Qwen 类的大部分逻辑）
- 工具调用循环（emaid.py 的 handle_llm_conversation）
- 状态注入（build_status）
- 数据集采集
- 提醒系统（reminder_scheduler.py）
- 睡眠管理（sleep/wake）

---

## 工具调用循环详细逻辑（从 emaid.py 提取）

当前 QQ Bot 的工具调用循环（`handle_llm_conversation`）有以下特殊处理，需要在公共模块中保留：

| 工具 | 特殊处理 |
|------|---------|
| `recall_memory` | 重置工具列表为 `get_general_tools()` |
| `search_on_internet` | 提取搜索主题 -> 调用 assistant 端点生成 400 字摘要 -> 发送合并转发消息 -> 剥离 `<reference_url:...>` 标签 |
| `move`/`decide_area`/`decide_school` | **导航状态机**：根据返回值（`[EXIT_AREA]`/`[EXIT_SCHOOL]`/数字）切换 `steps`，动态更新工具列表 |
| `access_website` | 访问失败时发送"网络不佳"提示 |
| 其他工具 | 重置工具列表为 `get_general_tools()`，长结果发送合并转发消息 |

**每轮循环的完整流程**：
1. 执行工具，获取 feedback
2. 特殊路由（上表）
3. 重建 status（时间/位置可能变化）
4. 调用 `send_feedback()` 将 observation 反馈给 LLM
5. LLM 返回新的 text 和/或 function_call
6. 如果有 text -> 发送响应
7. 如果 finish_reason 仍为 function_call -> 继续循环
8. 最多 6 轮（1 次初始调用 + 5 次反馈调用）

---

## 文件结构规划（草案）

```
项目根/
├── shared/                          <- 新增：公共模块
│   ├── context/
│   │   ├── __init__.py
│   │   ├── manager.py              <- ContextManager 类
│   │   ├── session.py              <- Session 数据模型
│   │   ├── history.py              <- 历史持久化（t_chat_history 读写）
│   │   ├── summarizer.py           <- 历史摘要压缩
│   │   └── fts.py                  <- FTS5 全文搜索
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py             <- ToolRegistry 工具注册表
│   │   ├── executor.py             <- 统一执行循环
│   │   ├── builtin/
│   │   │   ├── search.py           <- search_on_internet, access_website
│   │   │   ├── code.py             <- run_code_in_sandbox, interactive_code
│   │   │   ├── files.py            <- write_file, list_code_files, read_code_file
│   │   │   ├── git.py              <- git_command
│   │   │   ├── memory.py           <- recall_memory
│   │   │   ├── reminder.py         <- set/list/cancel_reminder
│   │   │   ├── navigation.py       <- move, decide_area/school, take_railway
│   │   │   ├── status.py           <- update_alias, go_to_sleep, set_daily_schedule
│   │   │   └── combat.py           <- sword_of_light
│   │   └── schemas.py              <- 所有工具的 JSON function schema 定义
│   └── dao/                         <- 共享 DAO（从 QQ Bot 和 Bilibili 提取）
│       ├── __init__.py
│       ├── engine.py               <- 共享数据库引擎
│       ├── map.py                  <- 地图（t_field/school/area/position）
│       ├── status.py               <- 爱丽丝状态（t_status）
│       ├── user.py                 <- 用户（t_user）
│       ├── chat_history.py         <- 聊天历史（t_chat_history + FTS5）
│       ├── reminder.py             <- 提醒（t_reminder）
│       └── tomb.py                 <- 墓地（t_tomb）
```

---

## 实施顺序

```
Phase 1: 上下文管理模块
  1.1 提取 DAO 层到 shared/dao/（从 QQ Bot 复制+清理）
  1.2 实现 ContextManager（会话、历史、摘要、时间标注）
  1.3 QQ Bot 改为调用 ContextManager（验证功能不变）

Phase 2: 通用工具迁移（低依赖的先做）
  2.1 文件操作工具（write/list/read_file, git_command）
  2.2 记忆召回（recall_memory）
  2.3 代码沙箱（run_code_in_sandbox, interactive_code）
  2.4 网页搜索（search_on_internet, access_website）
  2.5 提醒系统（set/list/cancel_reminder + APScheduler 迁移）

Phase 3: 游戏世界工具
  3.1 DAO 层已在 Phase 1 提取
  3.2 导航状态机迁移
  3.3 move/decide_area/decide_school/take_railway
  3.4 update_alias, go_to_sleep, set_daily_schedule

Phase 4: 渠道回调 + QQ 专属
  4.1 设计渠道回调接口
  4.2 sword_of_light 迁移
  4.3 提醒触发通知渠道
  4.4 睡眠模式管理迁移

Phase 5: QQ Bot 瘦身
  5.1 移除已迁移的代码
  5.2 简化 emaid.py
  5.3 简化 qwenOpenapi.py
  5.4 验证所有功能正常
```

---

## 其他待办

- [ ] `chatglmOpenapi.py` 清理（已弃用，可删除或标记 deprecated）
- [ ] Unity 项目目录 `unity/settings.json`（旧副本）清理
- [ ] 项目打包/发布方案（Unity 二进制通过 GitHub Releases）
- [ ] QQ Bot `.env` 中 `IMGROOT` 死配置清理
- [ ] 渠道配置编辑器的 `.env.prod` 写入测试验证
- [ ] Request Monitor 的 `SyntaxError: 2` 控制台噪音排查
- [ ] Chat 页面 `max_tokens` 参数可能需要从 persona 的 `max_chat_len` 读取而非 inference config
- [ ] 浏览器缓存问题：考虑给 index.html 加 `Cache-Control: no-cache` 响应头

---

## Git 分支状态

```
main:    80553f4  <- 最后推送的稳定版本
develop: 1f813a7  <- 当前工作分支（已推送）
```
