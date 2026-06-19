"""Standalone log viewer page for channel logs.

Returns a self-contained HTML page with a terminal-style log viewer
that auto-refreshes via polling the /admin/api/channels/{name}/log endpoint.
"""

from __future__ import annotations

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace;
    font-size: 13px;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }}
  .header {{
    background: #16213e;
    padding: 10px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #0f3460;
    flex-shrink: 0;
  }}
  .header h1 {{
    font-size: 16px;
    font-weight: 600;
    color: #e94560;
  }}
  .header .channel {{
    color: #53d8b2;
    font-size: 14px;
  }}
  .controls {{
    display: flex;
    gap: 15px;
    align-items: center;
  }}
  .controls label {{
    font-size: 12px;
    color: #aaa;
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
  }}
  .controls select {{
    background: #0f3460;
    color: #e0e0e0;
    border: 1px solid #1a5276;
    padding: 3px 8px;
    font-size: 12px;
    border-radius: 3px;
  }}
  .status {{
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 10px;
    background: #333;
  }}
  .status.connected {{ background: #1a472a; color: #53d8b2; }}
  .log-container {{
    flex: 1;
    overflow-y: auto;
    padding: 10px 20px;
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.5;
    font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace;
  }}
  .log-container span {{
    padding: 1px 0;
  }}
  .log-container::-webkit-scrollbar {{
    width: 8px;
  }}
  .log-container::-webkit-scrollbar-track {{
    background: #1a1a2e;
  }}
  .log-container::-webkit-scrollbar-thumb {{
    background: #0f3460;
    border-radius: 4px;
  }}
  .empty {{
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #555;
    font-size: 16px;
  }}
  .footer {{
    background: #16213e;
    padding: 6px 20px;
    font-size: 11px;
    color: #666;
    border-top: 1px solid #0f3460;
    flex-shrink: 0;
  }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Channel Log Viewer</h1>
    <span class="channel">{channel_name}</span>
  </div>
  <div class="controls">
    <label>
      <input type="checkbox" id="auto-refresh" checked> Auto-refresh
    </label>
    <select id="interval">
      <option value="1">1s</option>
      <option value="2" selected>2s</option>
      <option value="5">5s</option>
      <option value="10">10s</option>
    </select>
    <span id="status-badge" class="status">● polling</span>
  </div>
</div>
<div class="log-container" id="log-content">
  <div class="empty">Loading...</div>
</div>
<div class="footer">
  <span id="line-count">0 lines</span>
  &nbsp;|&nbsp; Auto-scroll: <span id="scroll-status">ON</span>
</div>
<script>
const API_URL = '{api_url}';
const logEl = document.getElementById('log-content');
const statusEl = document.getElementById('status-badge');
const lineCountEl = document.getElementById('line-count');
const scrollStatusEl = document.getElementById('scroll-status');
const autoRefreshCb = document.getElementById('auto-refresh');
const intervalSel = document.getElementById('interval');

let lastContent = '';
let userScrolledUp = false;
let timer = null;

logEl.addEventListener('scroll', () => {{
  const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 30;
  userScrolledUp = !atBottom;
  scrollStatusEl.textContent = atBottom ? 'ON' : 'OFF';
  scrollStatusEl.style.color = atBottom ? '#53d8b2' : '#e94560';
}});

async function fetchLog() {{
  try {{
    const resp = await fetch(API_URL + '?lines=500&format=html&_t=' + Date.now());
    if (!resp.ok) throw new Error(resp.status);
    const data = await resp.json();
    const content = data.log || '';
    if (content !== lastContent) {{
      lastContent = content;
      if (content.trim()) {{
        logEl.innerHTML = content;
        lineCountEl.textContent = content.split('\\n').length + ' lines';
      }} else {{
        logEl.innerHTML = '<div class="empty">(no log output yet)</div>';
        lineCountEl.textContent = '0 lines';
      }}
      if (!userScrolledUp) {{
        logEl.scrollTop = logEl.scrollHeight;
      }}
    }}
    statusEl.textContent = '● polling';
    statusEl.className = 'status connected';
  }} catch (e) {{
    statusEl.textContent = '● error';
    statusEl.className = 'status';
    if (!lastContent) {{
      logEl.innerHTML = '<div class="empty">Failed to load log</div>';
    }}
  }}
}}

function startPolling() {{
  stopPolling();
  fetchLog();
  timer = setInterval(fetchLog, parseInt(intervalSel.value) * 1000);
}}

function stopPolling() {{
  if (timer) {{ clearInterval(timer); timer = null; }}
  statusEl.textContent = '● paused';
  statusEl.className = 'status';
}}

autoRefreshCb.addEventListener('change', () => {{
  autoRefreshCb.checked ? startPolling() : stopPolling();
}});
intervalSel.addEventListener('change', () => {{
  if (autoRefreshCb.checked) startPolling();
}});

startPolling();
</script>
</body>
</html>"""


def render_log_viewer(channel_name: str, api_url: str) -> str:
    return HTML_TEMPLATE.format(
        title=f"{channel_name} - Channel Log",
        channel_name=channel_name,
        api_url=api_url,
    )
