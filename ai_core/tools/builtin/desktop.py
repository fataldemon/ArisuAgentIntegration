"""Desktop tools — screenshot, window management, mouse/keyboard control.

Screenshot supports full-screen or window-targeted capture, returns base64 so
the LLM can "see" the image. Control operations (click, type, scroll, keys, drag)
require user confirmation. Optional dependency: ``pyautogui``.
"""

import asyncio
import base64
import io
import os
import tempfile
from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


def _require_pyautogui():
    if not HAS_PYAUTOGUI:
        return "Error: pyautogui is not installed. Run: pip install pyautogui"
    return None


async def _screenshot(window_title: str = "", filename: str = "") -> str:
    err = _require_pyautogui()
    if err:
        return err

    loop = asyncio.get_event_loop()

    if window_title:
        try:
            windows = await loop.run_in_executor(None, pyautogui.getWindowsWithTitle, window_title)
        except Exception:
            windows = []
        if not windows:
            return f"Error: no window found matching {window_title!r}. Use list_windows to find available window titles."

        win = windows[0]
        try:
            win.activate()
            await asyncio.sleep(0.3)
        except Exception:
            pass
        try:
            left = win.left
            top = win.top
            w = win.width
            h = win.height
        except Exception:
            return f"Error: cannot get position of window {win.title!r}"

        try:
            img = await loop.run_in_executor(None, lambda: pyautogui.screenshot(region=(left, top, w, h)))
        except Exception as e:
            return f"Error capturing window {win.title!r}: {e}"
    else:
        try:
            img = await loop.run_in_executor(None, pyautogui.screenshot)
        except Exception as e:
            return f"Error taking screenshot: {e}"

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()
    b64 = base64.b64encode(raw).decode()
    w, h = img.size

    if filename:
        ws_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "game_workspace")
        os.makedirs(ws_root, exist_ok=True)
        path = os.path.join(ws_root, filename)
        with open(path, "wb") as f:
            f.write(raw)

    target = window_title or "full screen"
    return (
        f"Screenshot: {target} ({w}x{h}, {len(raw)} bytes)\n"
        f"[image,base64={b64}]"
    )


async def _list_windows() -> str:
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        windows = []

        def enum_callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    windows.append(buff.value)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    except Exception:
        err = _require_pyautogui()
        if err:
            return err
        windows = [w.title for w in pyautogui.getAllWindows() if w.title]

    if not windows:
        return "No visible windows found."
    lines = ["Visible windows:"]
    for i, title in enumerate(windows):
        lines.append(f"  [{i}] {title}")
    return "\n".join(lines)


async def _get_active_window() -> str:
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        return f"Active window: {buff.value} (hwnd={hwnd})"
    except Exception:
        err = _require_pyautogui()
        if err:
            return err
        try:
            w = pyautogui.getActiveWindow()
            return f"Active window: {w.title}" if w else "No active window detected."
        except Exception:
            return "Error: could not determine active window."


async def _click(x: int = 0, y: int = 0) -> str:
    err = _require_pyautogui()
    if err:
        return err
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: pyautogui.click(x, y))
    return f"Clicked at ({x}, {y})"


async def _type_text(text: str, interval: float = 0.05) -> str:
    err = _require_pyautogui()
    if err:
        return err
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: pyautogui.typewrite(text, interval=interval))
    return f"Typed {len(text)} characters"


async def _scroll(clicks: int = 3) -> str:
    err = _require_pyautogui()
    if err:
        return err
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: pyautogui.scroll(clicks))
    return f"Scrolled {clicks} click(s)"


async def _press_keys(keys: str) -> str:
    err = _require_pyautogui()
    if err:
        return err
    loop = asyncio.get_event_loop()
    key_list = [k.strip() for k in keys.split(",")]
    await loop.run_in_executor(None, lambda: pyautogui.hotkey(*key_list))
    return f"Pressed keys: {keys}"


async def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    err = _require_pyautogui()
    if err:
        return err
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: pyautogui.moveTo(x1, y1))
    await loop.run_in_executor(None, lambda: pyautogui.drag(x2 - x1, y2 - y1, duration=duration))
    return f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"


def register() -> None:
    reg = get_tool_registry()
    reg.register(ToolDef(
        name="screenshot",
        description=(
            "截取屏幕截图。可选通过窗口标题指定要截取的目标窗口（模糊匹配，如'Chrome'、'VSCode'），不指定则全屏截图。"
            "返回截图的base64编码图片供视觉分析，同时保存到工作空间。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "window_title": {"type": "string", "description": "要截取的窗口标题（模糊匹配），不填则全屏截图。"},
                "filename": {"type": "string", "description": "可选，保存截图的文件名（保存到工作空间）。"},
            },
            "required": [],
        },
        permission_level=PermissionLevel.READ,
        handler=_screenshot,
    ))
    reg.register(ToolDef(
        name="list_windows",
        description="列出桌面上所有可见窗口的标题，供截图或窗口操作时选择目标窗口。",
        parameters={"type": "object", "properties": {}, "required": []},
        permission_level=PermissionLevel.READ,
        handler=_list_windows,
    ))
    reg.register(ToolDef(
        name="get_active_window",
        description="获取当前前台（正在使用的）窗口的标题。",
        parameters={"type": "object", "properties": {}, "required": []},
        permission_level=PermissionLevel.READ,
        handler=_get_active_window,
    ))
    reg.register(ToolDef(
        name="click",
        description="在屏幕指定坐标(x, y)处点击鼠标。",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X坐标。"},
                "y": {"type": "integer", "description": "Y坐标。"},
            },
            "required": ["x", "y"],
        },
        permission_level=PermissionLevel.CONTROL,
        handler=_click,
    ))
    reg.register(ToolDef(
        name="type_text",
        description="模拟键盘输入文字到当前焦点窗口。",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要输入的文字。"},
                "interval": {"type": "number", "description": "每个字符之间的间隔秒数，默认0.05。"},
            },
            "required": ["text"],
        },
        permission_level=PermissionLevel.CONTROL,
        handler=_type_text,
    ))
    reg.register(ToolDef(
        name="scroll",
        description="滚动鼠标滚轮。正值向上滚动，负值向下滚动。",
        parameters={
            "type": "object",
            "properties": {
                "clicks": {"type": "integer", "description": "滚轮滚动格数，默认3。"},
            },
            "required": [],
        },
        permission_level=PermissionLevel.CONTROL,
        handler=_scroll,
    ))
    reg.register(ToolDef(
        name="press_keys",
        description="按下组合键。多个键用逗号分隔，如 ctrl,c（复制）、alt,tab（切换窗口）。",
        parameters={
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "逗号分隔的键名，如 ctrl,c 或 alt,f4。"},
            },
            "required": ["keys"],
        },
        permission_level=PermissionLevel.CONTROL,
        handler=_press_keys,
    ))
    reg.register(ToolDef(
        name="drag",
        description="从屏幕一点拖拽鼠标到另一点，可用于移动窗口或拖放操作。",
        parameters={
            "type": "object",
            "properties": {
                "x1": {"type": "integer"}, "y1": {"type": "integer"},
                "x2": {"type": "integer"}, "y2": {"type": "integer"},
                "duration": {"type": "number", "description": "拖拽持续时间（秒），默认0.5。"},
            },
            "required": ["x1", "y1", "x2", "y2"],
        },
        permission_level=PermissionLevel.CONTROL,
        handler=_drag,
    ))
