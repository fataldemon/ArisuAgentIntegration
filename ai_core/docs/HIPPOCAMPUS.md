# Hippocampus — 集中式上下文 / 记忆模块

> 内嵌于 AI Core 进程的会话上下文与记忆中枢。先以 HTTP 端点对外（供 QQ
> Bot 等渠道调用），后续 AI Core 可直接 `import` 进程内调用并逐步接管。

## 1. 现状（已完成：Phase 1.1 + 1.2，commit `2f7d48e`）

模块位于 `ai_core/hippocampus/`：

```
hippocampus/
├── db/engine.py            专用裸 sqlite3 engine（WAL + busy_timeout），
│                           独立于 QQ Bot 的 dbengine，指向共享 db/tendou_arisu.db
├── dao/chat_history.py     独立 chat_history DAO：建表 + FTS5 + save/load/recall，
│                           显式 session_id（去 contextvar），session_id 存入 group_id 列
├── context/
│   ├── session.py          Session：history/embedding_buffer/summary/last_reply/conversations
│   ├── manager.py          ContextManager（含后台自管截断 + per-session 截断锁）
│   ├── summarizer.py       summarize_fn 注入；默认接进程内 assistant（llm.chat.chat）
│   └── dataset.py          数据集采集（迁自 QQ Bot dataset_collection）
└── router.py               /ctx HTTP 端点
```

`main.py`：lifespan 启动时 `init_fts()`；`register_hippocampus_routes(app)` 挂载
`/ctx`；不动 `/v1`、`/assistant/v1`。

HTTP 端点：`POST /ctx/{sid}/message`、`GET /ctx/{sid}/history`、
`GET /ctx/{sid}/time-annotation`、`POST /ctx/{sid}/recall`、
`POST /ctx/{sid}/dataset[/flush]`、`GET /ctx/{sid}/session`。

### 关键决策
- hippocampus 内嵌 AI Core 进程；先 HTTP 暴露、后续进程内 import。
- 不迁 QQ Bot 其它 DAO（status/user/map/tomb/reminder 原样留 QQ Bot）。
- `session_id = 渠道 + id`（QQ 用纯 `{group_id}`，见接入约束）。
- 截断 + 摘要由 hippocampus 后台自管，渠道无感；摘要走进程内 assistant。

### 已验证（独立单测）
save/load 往返、FTS recall、时间标注（`X分钟过去了` / 长间隔重置）、
后台截断 + 摘要 + `is_summary=1` 落库、数据集 JSONL。修复了一个并发
`IndexError`（连续 save 触发多个后台截断交错）—— 已加 per-session 截断锁
+ drop_count 边界保护。

## 2. 下一步：QQ Bot 接入（方案 B 真正委托，带 env 开关默认关）

- 改 `qwenOpenapi.py`：`Qwen` 瘦成 HTTP 客户端（保留请求构造 / `_post` /
  `_process_response` / `call_assistant`），history/summary/time-annotation/
  dataset/save 改走 hippocampus HTTP。
- 改 `emaid.py`：`getLLM` / 封装方法 / handlers 改调客户端。
- 改 `reminder_scheduler.py`：遍历 `llm_list` 改用 hippocampus 端点。
- 新增 `qq_bot/src/skills/hippocampus_client.py`。
- `session_id` 用纯 `{group_id}` 保证历史连续。

## 3. 接入后会丧失 / 改变的功能（影响评估）

### 必须解决
- **B1 数据连续性**：session_id 用纯 `{group_id}` 复用既有 `t_chat_history`，
  否则上线瞬间全员失忆。
- **B2 history 顺序**：save 必须 `await`（串行有序），不可 `create_task`，
  否则 user/assistant 写入乱序导致上下文错乱。

### 需补 hippocampus 端点
- **B3** `/forget` 清空某 session（QQ `clear_memory`：只清内存不删 DB）。
- **B5/B6** 列举活跃 session + last_reply（reminder「选最近活跃群去睡觉」、
  sleep/wake 向各群注入系统消息）。

### 须保留在 QQ 侧
- **B4** `processing_cache`（打断 / abort）、`embedding_buffer`。

### 行为改变（待取舍）
- **A1 时间标注**：QQ 原版 `qwenOpenapi.py` 用 `.seconds`（有 bug：>1 天间隔
  取秒余数，2 天→0 不标注不重置，25h→误判「1小时」）；hippocampus 用
  `total_seconds()`（正确）。委托后 >12h 行为会变 —— 需定：对齐保留旧 bug
  还是接受修正。
- **A2 截断时机**：QQ 原版在「一轮对话结束后」串行触发；hippocampus 在
  「每次 save 后」后台触发，可能落在一轮中途 → 同轮后续请求 messages 长度
  不同 → 回复可能变。需对齐（轮末触发或感知轮边界）。
- **A3 sleep/wake 系统消息**：QQ 原版 `add_user_message_to_history` 只写内存
  （易失）；委托后走 `POST /message` → 持久化。
- **A4 时延**：每轮多次 localhost HTTP；save 改 await 阻塞主链路。

### 副作用
- **C1** 数据集文件位置变为 `ai_core/logs/datasets/`（原 `qq_bot/MyDataset-*.jsonl`
  不再更新）。
- **C2** 重启清记忆边界：改为 AI Core 重启才清 session 内存（都从 DB 恢复）。

## 4. Git

- `2f7d48e` feat: hippocampus context module (Phase 1.1+1.2)
