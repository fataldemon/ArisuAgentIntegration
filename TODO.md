# TODO：上下文管理 + 工具调用统一化

## 目标

将 QQ Bot 中的**上下文管理**和**工具调用**模块提取为 AI Core 的公共模块。所有渠道（QQ Bot、Bilibili、Unity、Chat 页面）共享同一套上下文管理和工具系统。

---

## ✅ Phase 1：上下文管理模块提取 — 已完成

**实际形态**：`ai_core/hippocampus/` — 内嵌于 AI Core 进程的独立模块（非原计划的 `shared/`）。channels 通过 HTTP 调用，后续 AI Core 可直接进程内 import。

### 已完成项

| 功能 | 状态 |
|---|---|
| 独立 chat_history DAO + 引擎（裸 sqlite3, WAL） | ✅ `hippocampus/db/engine.py` + `hippocampus/dao/chat_history.py` |
| ContextManager：会话 / 历史 / 摘要 / 时间标注 / recall / 数据集 | ✅ `hippocampus/context/manager.py` |
| 后台自管截断 + 摘要（渠道无感） | ✅ 每次 save_message 后自动触发 |
| FTS5 全文搜索初始化 | ✅ AI Core 启动时 `init_fts()` |
| HTTP 端点（turn-context / message / history / recall / clear / sessions） | ✅ `hippocampus/router.py`，挂 `/ctx` |
| QQ Bot 完全委托（去掉开关，唯一路径） | ✅ `qwenOpenapi.py` / `emaid.py` / `reminder_scheduler.py` 改造 |
| per-session 截断锁 + drop_count 边界保护 | ✅ 修复并发 IndexError |
| 进程树杀修复（taskkill /F /T /PID） | ✅ `channel_manager.py`，Stop 后端口 8080 无残留 |
| _monitor 误重启修复 | ✅ Windows `terminate()` 退出码 1 不再触发 `restart_on_crash` |

### 接入后行为变更（已确认的差异）

| 变更 | 说明 |
|---|---|
| 时间标注算法 | `.seconds` → `total_seconds()`（>1 天间隔正确显示，修正原 bug） |
| 历史持久化 | 原 `create_task` 异步写 → `await` 串行写（保证顺序） |
| 截断归属 | 原 QQ Bot 轮末触发 → hippocampus 后台自管 |
| 数据集位置 | `qq_bot/MyDataset-*` → `ai_core/logs/datasets/MyDataset-*` |
| `--reload` | 去掉（`nb run` 单进程，Stop 必干净） |

### PBS（保留在 QQ Bot 侧，未迁）

| 项 | 原因 |
|---|---|
| `message_buffer` / `group_locked` | 渠道编排，紧贴 QQ 事件循环 |
| `processing_cache`（打断/abort） | 请求并发控制 |
| `embedding_buffer` | 响应回填，下次请求带上 |
| `build_status`（含游戏态） | 依赖未迁的游戏 DAO |
| 导航 `steps` 状态机 | 待 Phase 3 |
| 工具循环 `handle_llm_conversation` | 待 Phase 2 |

---

## ✅ 额外完成：表情统一（character expressions）

| 项 | 状态 |
|---|---|
| 表情映射收归 persona.extra（70 条 label→image+favor） | ✅ `persona.json` |
| 表情图统一尺寸（480px 最长边） | ✅ `embedding/tendou_arisu/expression/image/` |
| 表情图处理工具 | ✅ `ai_core/core/expression_image.py` |
| 后端上传端点 + 供图端点 | ✅ `admin/routes.py` |
| Chat 前端动态拉取 expressions + 兜底 | ✅ `ChatView.vue` |
| QQ Bot 拉 persona expressions + 兜底 + favor 保留 | ✅ `emotion.py` |

### PBS（表情相关）

| 项 | 说明 |
|---|---|
| 表情上传前端 UI | 后端 endpoint 已有，CharactersView 缺上传编辑界面 |
| 图片尺寸微调 | 当前统一最长边 480，未来可能需要正方形画布 |

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
| 11 | `recall_memory` | time_range, keywords, limit, context_lines | SQLite FTS5 (t_chat_history_fts) | 中（hippocampus 已有 recall） |
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
| **SQLite FTS5** | QQ Bot 的 `init_fts()` — 已迁 ✅ | AI Core 启动时初始化 |
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
- ~~对话历史管理（Qwen 类的大部分逻辑）~~ ✅ 已迁
- 工具调用循环（emaid.py 的 handle_llm_conversation）
- 状态注入（build_status）
- ~~数据集采集~~ ✅ 已迁
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

## 文件结构（现状）

```
ai_core/
├── hippocampus/                       ← 上下文模块（替代原计划 shared/）
│   ├── db/engine.py                   ← 裸 sqlite3 引擎（WAL）
│   ├── dao/chat_history.py            ← 独立 chat_history DAO + FTS5
│   ├── context/session.py             ← Session 数据模型
│   ├── context/manager.py             ← ContextManager
│   ├── context/summarizer.py          ← 摘要（LLM 回调注入）
│   ├── context/dataset.py             ← 数据集采集
│   └── router.py                      ← /ctx HTTP 端点
├── core/
│   ├── expression_image.py            ← 表情图处理工具（缩放/路径/URL）
│   └── channel_manager.py             ← 进程树杀修复
├── embedding/tendou_arisu/
│   ├── persona.json                   ← expressions 映射（70 条）+ image_size
│   └── expression/image/              ← 15 张统一 480px 表情图
└── web/src/views/ChatView.vue         ← 动态拉取 expressions + 兜底

qq_bot/src/
├── skills/hippocampus_client.py       ← aiohttp HTTP 客户端
└── plugins/
    ├── qwenOpenapi.py                 ← Qwen 完全委托 hippocampus
    ├── emaid.py                       ← await add_user_message_to_history + 截断 no-op
    ├── reminder_scheduler.py          ← hippo.list_sessions 选群
    └── emotion.py                     ← 拉 persona expressions + 兜底 + favor 保留
```

---

## 实施顺序

```
✅ Phase 1: 上下文管理模块
   ✅ 1.1 独立 chat_history DAO + 引擎
   ✅ 1.2 ContextManager（会话、历史、摘要、时间标注）
   ✅ 1.3 QQ Bot 完全委托 hippocampus（去掉开关，唯一路径）

✅ 额外：表情统一
   ✅ persona.extra expressions + 480px 表情图 + QQ/Chat 双端打通

Phase 2: 通用工具迁移（低依赖的先做）
   2.1 文件操作工具（write/list/read_file, git_command）
   2.2 记忆召回（recall_memory）— hippocampus 已有
   2.3 代码沙箱（run_code_in_sandbox, interactive_code）
   2.4 网页搜索（search_on_internet, access_website）
   2.5 提醒系统（set/list/cancel_reminder + APScheduler 迁移）

Phase 3: 游戏世界工具
   3.1 导航状态机迁移
   3.2 move/decide_area/decide_school/take_railway
   3.3 update_alias, go_to_sleep, set_daily_schedule

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
- [ ] `qwenOpenapi.py` 死代码清理（`_conclude_summary` 等不再被调用）
- [ ] `emaid.py` `init_fts()` 移除（hippocampus 已自管）
- [ ] 表情上传前端 UI（CharactersView 加 expression 编辑界面）
- [ ] 摘要方式优化（保留更多信息）
- [ ] 表情图尺寸微调（可能需要正方形画布而非最长边等比）
- [ ] Unity 项目目录 `unity/settings.json`（旧副本）清理
- [ ] 项目打包/发布方案（Unity 二进制通过 GitHub Releases）
- [ ] QQ Bot `.env` 中 `IMGROOT` 死配置清理
- [ ] 渠道配置编辑器的 `.env.prod` 写入测试验证
- [ ] Request Monitor 的 `SyntaxError: 2` 控制台噪音排查
- [ ] Chat 页面 `max_tokens` 参数可能需要从 persona 的 `max_chat_len` 读取而非 inference config
- [ ] 浏览器缓存问题：考虑给 index.html 加 `Cache-Control: no-cache` 响应头
- [ ] hippocampus 端点鉴权（生产环境 `/ctx` 可能需要 Basic Auth 或 token）
- [ ] QQ Bot `--reload` 已去掉，需确认 channels.json（运行时）同步（gitignored，已手动改）

---

## Git 分支状态

```
main:    80553f4  <- 最后推送的稳定版本
develop: 4e13429  <- 当前工作分支（Phase 1 完成 + 表情统一 + Chat 会话持久化 + 修复）

---

## Phase 2：Agent 工具框架（设计已完成，待实施）

### 目标
把 AI Core 做成一个 Agent，拥有统一的工具注册表 + 权限模型 + 完整执行循环。
工具从 Chat 页面发起，QQ 等渠道不可用。

### 工具注册表（`ai_core/tools/`）

```
ai_core/tools/
├── __init__.py
├── schema.py            ToolDef / ToolResult / ToolPermission / ToolContext
├── registry.py          ToolRegistry 单例 (register / list / call)
├── permissions.py       权限检查 + PendingManager 确认队列
└── builtin/
    ├── filesystem.py     文件操作 (read/write/edit/list/search/delete)
    ├── terminal.py       终端命令 (白名单/黑名单)
    ├── desktop.py        桌面截屏/点击/滚轮/键盘 (pyautogui+pywin32)
    └── process.py        进程管理 (list/get/kill)
```

### 工具清单

| 类别 | 工具 | 权限 | 依赖 |
|---|---|---|---|
| 文件读 | read_file, list_directory, search_files, search_content | filesystem:read | os |
| 文件写 | write_file, edit_file, delete_file | filesystem:write（需确认） | os |
| 终端 | terminal_command | terminal:exec（需确认） | subprocess |
| 桌面读 | screenshot, list_windows, get_active_window | desktop:read | pyautogui |
| 桌面控制 | click, type_text, scroll, press_keys, drag | desktop:control（需确认） | pyautogui/pywin32 |
| 进程读 | list_processes, get_process_info | process:read | os |
| 进程控制 | kill_process | process:write（需确认） | os |

### 权限模型
- 读操作 → 自动通过
- 写/控制/终端操作 → 人工确认（Chat 页面弹窗 / 桌面托盘系统弹窗）
- WebUI 权限管理页：设置工具免审核白名单（离线时生效）

### 执行流程

```
用户发消息 → POST /v1/chat/completions (非流式, tools 注入)
  → LLM 返回 function_call
  → 读类工具 → 直接 POST /v1/tools/execute → 追加结果 → 继续
  → 写/控制类 → 前端弹确认窗 → 用户允许/拒绝 → 执行/跳过 → 继续
```

### 分阶段

| 阶段 | 内容 |
|---|---|
| 2.0 | ToolRegistry 骨架 + echo 测试工具 + Agent Loop 集成 + POST /v1/tools/execute |
| 2.1 | 文件工具 (filesystem.py: 7个) + 终端命令 (terminal.py) + 工作区隔离 |
| 2.2 | Chat 前端 inline 确认弹窗 |
| 2.3 | 桌面截屏 + 进程管理 + 桌面托盘程序 |
| 2.4 | WebUI 权限管理页（免审核白名单） |
| Phase 4 | QQ 渠道回调入口 + hybrid 工具 (sword_of_light 等) |

### 渠道回调框架（预留）
- 渠道启动时向 AI Core 注册 callback_url + capabilities
- 混合工具（hybrid）：AI Core 执行 DB 部分, 回调渠道执行 QQ API 部分
- 桌面托盘确认程序也走回调框架