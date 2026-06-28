# TODO：ArisuAgent 集成项目 — 开发路线图

> 最后更新：2026-06-28（develop 分支）

## 项目现状

AI Core（FastAPI + Vue Admin UI）是天童爱丽丝的统一 AI 后端，管理 QQ Bot / Bilibili / Unity / Chat 多渠道。
当前已完成：上下文管理（hippocampus）、工具框架（registry + 22 个 builtin）、权限模型（capability allow/ask/deny + 按目录文件规则）、网页搜索（SearXNG + CDP 浏览器）。

---

## ✅ 已完成

### Phase 1：上下文管理（hippocampus）
- `ai_core/hippocampus/`：独立 chat_history DAO（WAL + FTS5）、ContextManager（会话/历史/摘要/时间标注/recall/数据集）、HTTP 端点挂 `/ctx`
- QQ Bot 完全委托 hippocampus（去掉开关，唯一路径）
- 并发安全修复（per-session 截断锁 + drop_count 边界保护 + 进程树杀 + monitor 误重启）

### Phase 2：Agent 工具框架
- **ToolRegistry + ToolDef schema**：`ai_core/tools/{schema,registry,permissions}.py`
- **6 个工具组**（系统操作/网络检索/记忆召回/技能知识/提醒日程/游戏世界设定/测试）
- **22 个 builtin 工具**：文件操作 7 个、终端 1 个、桌面 8 个、进程 3 个、技能 2 个、网页 2 个（web_search + access_website）、测试 1 个
- **元数据驱动引导**：`_build_tool_guidance(channel, identity)` 按组/分类渲染系统提示词，用模型原生 `<tool_call>` 文本格式做 few-shot
- **权限模型**：
  - 全局能力 `allow/ask/deny`（权限管理页）
  - 工作空间外文件：按目录规则（allow 自动 / deny 拒绝 / 无匹配弹窗）
  - 弹窗四选项：允许本次 / 始终允许该目录 / 请求解释（LLM 解释操作）/ 拒绝
- **文件工具 scope 参数**：`scope=workspace`（沙箱）/ `scope=system`（工作空间外，按目录规则授权）
- **Chat 页面 agent loop**：client-side `runAgentLoop`，多轮工具调用 + 四选项确认弹窗 + `<tool_call>` 文本持久化
- **网页搜索**：SearXNG（自部署 Docker，免 key，Bing 可用）+ 图片搜索
- **网页访问**：CDP 浏览器管理器（真 Chrome 优先 + 反检测 + Playwright Chromium 兜底），`access_website(url, close, screenshot)`，动态内容等待 + 滚动 + `bring_to_front`
- **builtin 工具仅下发给 chat 渠道**（`_BUILTIN_CHANNELS = {"chat"}`），不泄漏给 QQ/default

### 表情统一
- persona.extra expressions（70 条 label→image+favor）+ 480px 表情图
- Chat 前端动态拉取 + QQ Bot 兜底

### Bug 修复（本会话）
- QQ Bot：reminder_scheduler hippo 导入、recall_memory 委托 hippocampus、`<think>` 切片 off-by-one、set_talker_name 列表名、area_map matcher、hikari_yo try/except、image_process 段类型 + @DeprecationWarning
- DAO None 守卫：user.py / tomb.py / map.py（+ session.close）
- AI Core：工具去重（list_skills/read_skill）、channel_manager restart 逻辑修复、chat 工具调用上下文 `<tool_call>` 文本持久化（对齐 QQ）
- 前端：keep-alive 定时器泄漏（MonitorView/ChannelsView 改 onActivated/onDeactivated）、ChatView agent loop + 四选项弹窗
- start.bat：CRLF 行尾 + `%ProgramFiles(x86)%` 括号陷阱 + `.installed` 门禁去除 + 无条件 pause + 日志
- SearXNG：`SEARXNG_SECRET`（修崩溃）+ docker compose（修 Windows 挂载）+ 超时 10s（Bing 能返回）+ `docker rm -f` 自动重建

---

## Phase A：知识管理与记忆系统

**目标**：让 AI 自主搜索、存储、检索知识，弥补被动 RAG 的不足。支持共享知识（所有用户）+ 个人记忆（per-user）。

### 设计

| 类型 | 存储位置 | 检索 | 现有基础 |
|---|---|---|---|
| 共享知识 | `embedding/_shared/knowledge/` | `process_embedding` 已自动搜 | ✅ `add_knowledge()` 增量写入已有 |
| 个人记忆 | `embedding/_user_<QQ号>/memory/`（虚拟角色 + `memory` subject） | `process_embedding` 新增分支 | `memory` 在 VALID_SUBJECTS 白名单，`generate_vector` 支持任意 subject |

**per-user 隔离方案**：把每个用户当成一个"虚拟角色"（`_user_<uid>`），零 schema 改动，复用现有 character/subject 架构。QQ 用 QQ号，Bilibili 用 B站账号，Chat 用 identity。

### 任务清单

| # | 任务 | 依赖 | 详情 |
|---|------|------|------|
| A1 | 泛化增量写入函数 | — | 从 `embedding.py:add_knowledge(content, character)` 抽出 `add_to_subject(content, character, subject)`，去掉 subject 硬编码 `"knowledge"`。逻辑：读现有 .mem → append 新段落 → 增量 `idx.add(embeddings)` → 写回 index.faiss + materials.jsonl。不一致时 fallback 全量 `generate_vector` 重建。 |
| A2 | `save_knowledge` 工具 | A1 | 参数：`content: str, scope: "shared"|"user" = "shared", tags: str = ""`。scope=shared → `add_to_subject(content, "_shared", "knowledge")`。scope=user → `add_to_subject(content, "_user_<uid>", "memory")`。tags 附加到 .mem 行尾 `##tag1##tag2`。capability `memory.write`，默认 allow（AI 完全自主）。新工具组 `记忆管理`。 |
| A3 | `search_knowledge` 工具 | A1 | 参数：`query: str, scope: "shared"|"user"|"all" = "all"`。调 `vector_search(query, top_k, character, subject, instruct)` → 返回命中段落文本。scope=all 时分别搜 `_shared/knowledge` + `_user_<uid>/memory`，合并结果。capability `memory.read`，allow。 |
| A4 | `delete_knowledge` 工具 | A1 | 参数：`line_text: str, scope: "shared"|"user" = "user"`。读对应 .mem → 删匹配行 → `generate_vector` 全量重建。用"按内容匹配删除"而非 row_id（更直观，AI 知道自己写了什么）。capability `memory.write`，allow。 |
| A5 | per-user 虚拟角色创建 | A2 | `_user_<uid>` 目录按需创建（首次 save_knowledge scope=user 时）。`data_store.create_character("_user_<uid>")` 会预建所有 subject 目录。user_id 来源：QQ 传 QQ号，Chat 传 identity 字符串，Bilibili 传账号。 |
| A6 | `process_embedding` 加 memory 搜索 | A5 | 当前 `process_embedding`（embedding.py:480）固定搜 `setting` + `_shared/knowledge`。新增第三步：搜 `_user_<uid>/memory`（top_k=3），拼进 `embeddings_text`。需把 user_id 传入 `process_embedding`（新增参数 `user_id: str = ""`）。 |
| A7 | user_id 传播 | A5 | `ChatCompletionRequest` 加 `user_id: Optional[str] = ""` 字段。QQ Bot 的 `qwenOpenapi.py` 传 `user_id=event.user_id`。Chat 页面传 `user_id=identity`。chat_on_setting / chat_on_setting_stream 把 user_id 传给 `process_embedding`。工具通过 context var（类似 QQ Bot 的 `current_group_id`）获取当前 user_id。 |
| A8 | UI 补 memory 管理 | A5 | CharactersView 的 subject 下拉加 `memory`（当前只有 setting/expression/knowledge）。character 列表（`list_kb_characters`）改为**不排除** `_user_*` 开头的目录（当前排除 `_` 开头），或单独加一个"个人记忆"入口。编辑/删除走现有 .mem 文件 CRUD + rebuild 流程。 |
| A9 | 引导文案 | A2 | groups.py 的 `记忆管理` 组（或归入记忆召回组）加引导："学到了有价值的新知识时，调用 save_knowledge 保存到知识库。搜索后综合的信息也值得保存。过时的知识可以删除。" |

### 搜索→学习→记忆完整流程
```
用户："山海经有什么新活动？"
  ├─ AI: web_search → 5 条结果
  ├─ AI: access_website(萌娘百科 URL) → 读全文
  ├─ AI: save_knowledge("山海经近期活动：五尘降临...", scope="shared")
  │     → 增量写入 _shared/knowledge 的 FAISS
  ├─ AI: 回答用户
  └─ 下次任何人问山海经 → process_embedding 自动命中 → 不用再搜

用户："你还记得我上次说的那个策略吗？"
  ├─ process_embedding 自动搜 _user_<uid>/memory → 命中
  └─ AI 也能主动 search_knowledge(query, scope="user") 深挖
```

### 风险与注意事项
- `add_knowledge` 的增量写入需并发安全（单进程 asyncio.Lock，已有 `data_store._get_lock`）
- `generate_vector` 全量重建是同步阻塞操作 → 必须 `asyncio.to_thread` 包裹
- `.mem` 行格式：每行一条记录，行尾可附 `##tag1##tag2`
- 虚拟角色目录会随用户数增长 → 可定期清理不活跃用户的记忆

---

## Phase B：RAG 多模态（图片支持）

**目标**：知识库支持图片——文本描述做向量检索，图片作为 sidecar payload 注入 LLM 视觉。不需要换多模态 embedding 模型。

### 设计

`MaterialRecord` 已有 `type="image"` + `media_ref` 字段（schema 就绪但未使用）。方案：
- `.mem` 文件的一行可以包含**文本描述 + 图片引用**：`这是一张山海经高中的外观图 ##山海经##学校\n[image,file=shanhaijing.png]`
- `generate_vector` 处理时：文本描述 → 向量化；图片路径 → `media_ref`
- `process_embedding` 检索命中含图片的段落时，在返回文本里输出 `[image,file=xxx.png]` → `content_normalizer` 自动转视觉内容
- 图片文件存 `embedding/<character>/<subject>/binaries/`

### 任务清单

| # | 任务 | 依赖 | 详情 |
|---|------|------|------|
| B1 | `.mem` 格式扩展 | — | `_gather_paragraphs_from_mem`（embedding.py:146-179）增加解析 `[image,file=xxx]` 行：识别为 type="image" 的段落，text=前一行文本（描述），media_ref={"source": "xxx"}。图片文件在 `binaries/` 或 `image/` 目录。 |
| B2 | `generate_vector` 处理图片行 | B1 | `build_paragraph_records` 已支持 type/media_ref 字段。向量仍用文本描述编码。图片文件路径存入 `MaterialRecord.media_ref`。 |
| B3 | `process_embedding` 返回图片引用 | B2 | `find_material_by_index`（embedding.py:456）返回文本时，检查该段落是否有 media_ref；有则在文本末尾追加 `[image,file=<media_ref.source>]`。content_normalizer 会把它转成视觉内容。 |
| B4 | `save_knowledge` 支持图片 | B1,A2 | 参数加 `image_path: str = ""`。save_knowledge 时如果有 image_path，在 .mem 里写两行：描述行 + `[image,file=<filename>]` 行。图片文件复制到 `binaries/`。 |
| B5 | `access_website` 截图存入知识库 | B4 | AI 搜到有用网页 → `access_website` 截图 → `save_knowledge(content, image_path=screenshot_path)`。需要 access_website 把截图存到 workspace 而非只返回 base64。 |
| B6 | 知识库管理 UI 支持图片 | B1 | SharedKnowledgeView / CharactersView 的 .mem 编辑器支持图片引用语法预览。上传图片到 binaries/。 |

### 注意事项
- embedding 模型不变（`DMetaSoul/Dmeta-embedding`，文本 only）。文本描述驱动检索，图片是关联 payload。
- `content_normalizer.py` 已支持 `[image,file=...]` → 视觉内容转换（read_file 已在用）。
- 图片大小应控制（如 480px 最长边，同表情图标准），避免 embedding 目录膨胀。

---

## Phase C：游戏世界观工具迁移

**目标**：将 QQ Bot 的导航状态机 + 7 个游戏工具迁到 AI Core，保留多步导航的探索玩法。

### 核心挑战

1. **动态工具下发**：导航状态机每轮切换可用工具集（move/decide_area/decide_school），需要扩展 AI Core 的工具框架支持 per-session 动态工具。
2. **全局变量→per-session**：QQ Bot 的 `available_move_targets` 等是模块级全局（无锁，并发不安全）。迁移后必须改成 per-session 返回值。
3. **游戏 DB**：`t_status`（单例 Alice 位置/睡眠）、`t_position`/`t_area`/`t_school`（静态地图）、`t_user`（per-user 别名/好感）。用 SQLite WAL 共享，后续 qq_bot 游戏逻辑全迁 AI Core。
4. **步内渲染**：每步移动在 QQ 里推一条合并转发消息 → 抽成渠道回调（非必须，可先不做）。

### 任务清单

| # | 任务 | 依赖 | 详情 |
|---|------|------|------|
| C1 | 动态工具下发框架扩展 | — | 当前 `_channel_builtin_tools(channel)` 返回静态工具集。扩展为支持 per-session 状态：session 持有 `steps`（0/1/2），`_channel_builtin_tools` 根据 steps 返回不同的导航工具 + 动态填充 options description。需要 session-scoped 工具状态存储（in-memory dict keyed by session_id，或 hippocampus session metadata）。 |
| C2 | 导航状态机迁移 | C1 | 从 `emaid.py:handle_llm_conversation:1001-1078` 提取纯函数 `next_move_state(steps, feedback) -> (new_steps, tool_list, system_notice)`。feedback 值：`[EXIT_AREA]`→steps=1、`[EXIT_SCHOOL]`→steps=2、数字→下钻/回退。`move_tool(steps, school_id, area_id)` 逻辑搬过来。 |
| C3 | move/decide_area/decide_school/take_railway | C2 | 4 个导航工具。逻辑从 `services.py:73-144` + `status.py:160-259` 提取为纯函数。`move_position(position_id)` 写 t_status。`find_route(steps, school_id, area_id)` 改为返回 `(options_list, desc)` 元组（不再写全局变量）。options 字母含义：E=退出区域/学校、H=回家(63)、S=去沙勒(10)、数字=具体地点ID。 |
| C4 | 游戏 DAO 迁移 | — | `map.py`（Field/School/Area/Position 查询）、`status.py`（move_position/move_default_position/find_route/check_railway/get_status_description/load_sleep_state/save_sleep_state/load_schedule/save_schedule）的纯 DB 逻辑搬到 `ai_core/game/`。engine 连同一个 SQLite（WAL 模式）。 |
| C5 | 游戏 DB 共享 | C4 | AI Core game engine 连 QQ Bot 的同一个 SQLite 文件（`SQLALCHEMY_DATABASE_URL`）。WAL 模式允许跨进程并发读+单写。后续 qq_bot 游戏逻辑全迁 AI Core 后，qq_bot 不再直接访问游戏 DB。 |
| C6 | update_alias / go_to_sleep / set_daily_schedule | C4 | update_alias 写 t_user.alias。go_to_sleep 写 t_status（is_sleeping/sleep_phase）+ move_position(63)（回家）。set_daily_schedule 写 t_status（sleep/wake hour/minute）。 |
| C7 | QQ 合并转发 → 渠道回调 | C3 | 导航步内渲染（emaid.py 的 send_system_forward）抽成回调。AI Core 返回 system_notice 文本，渠道决定是否渲染（QQ→合并转发、Chat→系统消息气泡、Web→折叠面板）。非必须，可先不渲染。 |
| C8 | 游戏工具引导 | C3 | groups.py 的 `游戏世界设定` 组引导更新，说明 move 工具的 options 含义（E/H/S/数字）和导航流程。 |

### 导航状态转移图
```
steps=0 [move: 选同区域地点 + E/H/S]
   ├─ 数字 → move_position(数字) → DONE → steps=0
   ├─ E → [EXIT_AREA] → steps=1
   ├─ H → move_position(-2) → 回家 → DONE
   └─ S → move_position(-3) → 去沙勒 → DONE

steps=1 [decide_area: 选同校区区域 + E/H/S]
   ├─ 数字 → move_default_position(0, area_id) → steps=0, move_tool(0, 0, area_id)
   ├─ E → [EXIT_SCHOOL] → steps=2
   └─ H/S → move_position(-2/-3) → DONE

steps=2 [decide_school: 选校区 + H/S]
   ├─ 数字 → move_default_position(school_id, 0) → steps=1, move_tool(1, school_id, 0)
   └─ H/S → move_position(-2/-3) → DONE
```

---

## Phase D：QQ Bot → AI Core 工具迁移

**目标**：逐步将 QQ Bot 工具委托给 AI Core，QQ Bot 瘦身为薄桥接层。

| # | 任务 | 依赖 | 详情 |
|---|------|------|------|
| D1 | QQ search 改调 AI Core `web_search` | — | QQ Bot 的 `services.py:search_on_internet` 改为 HTTP 调 AI Core 的 `/v1/tools/execute`（tool_name=web_search）。删 `online_search.py`。QQ 侧的搜索后处理（提取主题→摘要→合并转发）保留在 QQ 编排层，或也让 agent loop 做。 |
| D2 | QQ access_website 改调 AI Core | D1 | 同理，`access_page_func` → HTTP 调 AI Core access_website。 |
| D3 | reminder 系统迁移 | — | APScheduler 从 QQ Bot 迁到 AI Core。提醒触发时通过渠道回调通知 QQ 发消息。`t_reminder` 表迁到 AI Core 或共享 SQLite。 |
| D4 | sleep 状态机迁移 | D3 | SLEEP_MODE/SLEEP_PHASE 全局变量 → AI Core 进程内状态（持久化到 t_status）。自动入睡/起床的 APScheduler 任务迁到 AI Core。 |
| D5 | sword_of_light 渠道回调 | — | AI Core 写 t_tomb + 返回渠道动作指令（"禁言 user_id 10分钟"），QQ Bot 收到回调执行 set_group_ban。 |
| D6 | QQ Bot 死代码清理 | D1-D5 | 删 chatglmOpenapi.py、init_fts、shorten_history、summarize_history、_conclude_summary。简化 emaid.py（移除已迁逻辑）。 |

### 渠道回调机制设计
```
渠道启动 → 向 AI Core POST /v1/channels/register
  {channel_id, callback_url, capabilities: ["send_message","ban_user","forward_msg"]}

AI Core 执行工具产生渠道动作 → POST callback_url
  {action: "ban_user", user_id, duration}
  {action: "send_message", content, segments}
  {action: "send_forward", nodes[]}
```

---

## Phase E：文档（面向开放给其他用户）

| # | 任务 | 详情 |
|---|------|------|
| E1 | README 重写 | 项目简介 + 一键启动 + **前置依赖矩阵**（核心 vs 每个可选功能各自需要什么、怎么装）。中文为主。 |
| E2 | 前置依赖矩阵 | 核心必需：Python 3.10+ / Node 18+（start.bat 自动装）。可选：Docker（SearXNG + 代码沙箱）/ Chrome（CDP 浏览器）/ Playwright Chromium（无 Chrome 时兜底，自动装）/ OneBot 实现（QQ）/ B站开放平台 API / Unity 构建 / OCR HTTP 服务 / TTS VITS 服务 / LLM provider（vllm/远程）。每项写清"要什么、装了能干什么、不装会怎样（优雅降级）"。 |
| E3 | 修过时文档 | ai_core/README.md（"Gradio"→"Vue SPA"）。qq_bot/README.md 重写（当前是 nb create 模板废稿）。 |
| E4 | 各渠道配置指南 | QQ：OneBot WS URL、master_id、bot_id、.env 配置。Bilibili：开放平台 API 密钥。Unity：settings.json（WebSocket URL、TTS 地址）。 |
| E5 | start 脚本注释 | 可选步骤（SearXNG/Playwright/Chromium）标注"不需要可跳过"。Docker 未安装时的提示信息。 |
| E6 | vllm 配置说明 | `--enable-auto-tool-choice --tool-call-parser qwen3_coder` 必须带。embedding 模型路径。端口配置。 |

---

## Phase F：基础设施优化

| # | 任务 | 详情 |
|---|------|------|
| F1 | SearXNG 代理动态检测 | start 脚本探测 localhost:7897（或可配端口）→ 有代理时挂载带代理的 settings.yml（`outgoing.proxies`），没代理时用直连（Bing only）。两个 settings 文件 + compose override。 |
| F2 | access_website 流式标签过滤 | `<tool_call>` 标签在 streaming 时短暂闪现给前端。backend 端加 tag 感知过滤：检测到 `<tool_call>` 开头时停止 yield content delta，直到 `</tool_call>` 闭合。 |
| F3 | start 脚本跨平台 Chrome 检测 | mac/linux 的 Chrome 路径检测完善（当前只写了 Windows + 基本的 mac/linux）。 |
| F4 | requirements.txt 清理 | 移除死依赖 `gradio>=5.0`（ai_core/requirements.txt）。根目录和 ai_core 两份 requirements 统一或明确分工。 |
| F5 | qq_bot 死代码清理 | chatglmOpenapi.py（整文件删除）、chat_history.py 的 init_fts/save_chat_record/load_recent_history（无人调用）、functions.py 的 func_move_random/func_walk/search_for_item、voice.py 废弃函数、user_status_process.py（整文件无引用）。 |
| F6 | ChatView streamChat 捕获 `delta.tool_calls` | 当前只捕获 `delta.function_call`（legacy 单数）。加 `delta.tool_calls`（数组格式）兜底，防 vllm 新版格式变化。 |
| F7 | index.html 缓存控制 | main.py 的 /admin 响应加 `Cache-Control: no-cache`，避免部署后用户拿到旧前端。 |
| F8 | hippocampus 端点鉴权 | 生产环境 `/ctx` 端点可能需要 Basic Auth 或 token（当前完全无鉴权）。 |

---

## 其他待办（杂项）

- [ ] 表情上传前端 UI（CharactersView 加 expression 编辑界面 + 图片上传）
- [ ] 摘要方式优化（保留更多信息，当前 hippocampus 摘要较粗略）
- [ ] Chat 页面 `max_tokens` 参数从 persona 的 `max_chat_len` 读取而非硬编码 15000
- [ ] Unity 项目打包/发布方案（GitHub Releases）
- [ ] 渠道配置编辑器的 `.env.prod` 写入测试验证
- [ ] Request Monitor 的 `SyntaxError: 2` 控制台噪音排查

---

## Git 分支状态

```
main:    80553f4  <- 最后推送的稳定版本
develop: 当前工作分支（Phase 1 + Phase 2 工具框架 + 权限模型 + 网页搜索 + 大量修复）
```

---

## 实施顺序（推荐）

```
✅ Phase 1: 上下文管理（hippocampus）
✅ Phase 2: Agent 工具框架 + 22 个 builtin + 权限 + 网页搜索

Phase A: 知识管理与记忆系统
   A1 泛化 add_to_subject
   A2-A4 save_knowledge / search_knowledge / delete_knowledge 工具
   A5-A7 per-user 虚拟角色 + process_embedding + user_id 传播
   A8-A9 UI + 引导

Phase B: RAG 多模态（图片）
   B1-B3 .mem 格式扩展 + generate_vector + process_embedding 返回图片
   B4-B6 save_knowledge 支持图片 + 截图存知识 + UI

Phase C: 游戏世界观工具
   C1 动态工具框架扩展
   C2-C3 导航状态机 + move/decide 工具
   C4-C6 游戏 DAO + DB + 其余工具
   C7 合并转发→回调（可后置）

Phase D: QQ Bot → AI Core 迁移
   D1-D2 搜索/访问改调 AI Core
   D3-D4 提醒/睡眠迁移
   D5 sword_of_light 回调
   D6 QQ Bot 瘦身

Phase E: 文档（随时可做，建议 Phase A 完成后）

Phase F: 基础设施（穿插进行）
```
