# ArisuAgentIntegration

天童爱丽丝 (Tendou Arisu) AI 代理大仓 — 统一维护 QQ 机器人、B站直播、Unity 桌面宠物等渠道。

## 目录结构

```
ArisuAgentIntegration/
├── ai_core/       # AI 核心服务 (FastAPI + Gradio Admin UI)
├── qq_bot/        # QQ 机器人 (NoneBot2 + OneBot v11)
├── bilibili/      # B站直播弹幕交互 (Streamlit + blivedm)
├── unity/         # Unity 桌面宠物构建产物 (仅 Windows)
├── venv/          # 统一虚拟环境 (gitignored)
├── run.py         # 一键启动 AI 核心
├── start.sh       # Linux 启动脚本 (venv + run)
└── start.bat      # Windows 启动脚本
```

## 快速开始

```bash
# Linux
./start.sh

# Windows
start.bat
```

首次运行会自动创建 venv 并安装依赖。

## 渠道管理

启动后访问 http://localhost:8000/admin → **Channels** 标签页：

- 查看各渠道运行状态
- 手动 Start / Stop / Restart
- 独立标签页查看实时日志

渠道**不会**随 AI 核心自动启动，完全通过 WebUI 手动控制。

## 渠道说明

| 渠道 | 目录 | 启动命令 | 平台 |
|------|------|---------|------|
| qq_bot | `qq_bot/` | `nb run --reload` | 全平台 |
| bilibili | `bilibili/` | `streamlit run webui.py` | 全平台 |
| unity | `unity/` | `AliceBotDesktop.exe` | 仅 Windows |

Unity 构建产物不入 git，需从 `F:\UnityLib\NewVersion\TendouArisu` 手动复制到 `unity/`。

## 配置

各渠道的环境变量：
- `qq_bot/.env` — OneBot WS URL、QQ 号等
- `bilibili/.env` — B站开放平台 API 密钥
- `unity/settings.json` — WebSocket URL、TTS 地址等

模板文件 `*.example` 已入 git，实际配置文件不入 git（含密钥）。
