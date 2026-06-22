import os
import re

import requests
from dotenv import load_dotenv

from src.dao.user import favor_change

load_dotenv()
root_url = os.environ.get("ABS_ROOT")
AI_CORE_URL = os.environ.get("AI_CORE_URL", "http://localhost:8000")
CHARACTER = os.environ.get("CHARACTER", "tendou_arisu")

# 内置默认映射（兜底）：label -> (image_filename, favor_delta)
# 当无法从 AI Core 拉取角色表情时使用本地 emoji 原图。
_DEFAULT_EXPR = {
    "认真": ("angry.png", 0), "坚定": ("angry.png", 0), "承诺": ("angry.png", 0),
    "生气": ("angry.png", -5), "急切": ("angry.png", 0), "烦恼": ("screwup.png", 0),
    "专注": ("awake.png", 0), "诚实": ("awake.png", 0), "期待": ("smile.png", 1),
    "回答": ("awake.png", 0), "回忆": ("thinking.png", 0), "发愣": ("awake.png", 0),
    "察觉": ("awake.png", 0), "建议": ("smile.png", 0), "好奇": ("awake.png", 1),
    "自信": ("confident.png", 0), "自豪": ("confident.png", 0), "解释": ("smile.png", 0),
    "失望": ("awkward.png", -1), "委屈": ("cry.png", -2), "伤心": ("cry.png", -3),
    "高兴": ("smile.png", 1), "开心": ("happy.png", 2), "欢迎": ("smile.png", 1),
    "崇拜": ("smile.png", 2), "愉快": ("smile.png", 1), "贴心": ("smile.png", 1),
    "赞同": ("smile.png", 1), "邀请": ("smile.png", 0), "兴奋": ("happy.png", 2),
    "快乐": ("happy.png", 1), "难过": ("awkward.png", -1), "为难": ("awkward.png", 0),
    "紧张": ("awkward.png", 0), "困惑": ("awkward.png", 0), "困扰": ("awkward.png", -1),
    "疑惑": ("awkward.png", 0), "害怕": ("sweating.png", -2), "无奈": ("sweating.png", -1),
    "平和": ("plain.png", 0), "无聊": ("plain.png", 0), "慌张": ("screwup.png", 0),
    "害羞": ("shy.png", 0), "羞涩": ("shy.png", 0), "微笑": ("confident.png", 0),
    "惊喜": ("smile.png", 2), "理解": ("smile.png", 0), "喜悦": ("smile.png", 1),
    "担忧": ("sweating.png", 0), "流汗": ("sweating.png", 0), "尴尬": ("sweating.png", -1),
    "犹豫": ("awkward.png", 0), "震惊": ("sweating.png", 0), "惊讶": ("sweating.png", 0),
    "思考": ("thinking.png", 0), "沉思": ("thinking.png", 0), "否认": ("thinking.png", 0),
    "睡觉": ("thinking.png", 0), "陈述": ("plain.png", 0), "祈祷": ("thinking.png", 1),
    "拒绝": ("angry.png", -1), "警惕": ("angry.png", -1), "感动": ("touching.png", 2),
    "感激": ("touching.png", 2), "道歉": ("sweating.png", 1), "可爱": ("happy.png", 1),
    "俏皮": ("happy.png", 1), "调皮": ("happy.png", 1), "卖萌": ("happy.png", 1),
    "眨眼": ("happy.png", 1),
}

# 运行时映射：label -> {"image": filename, "favor": int}
_expr_map = {k: {"image": v[0], "favor": v[1]} for k, v in _DEFAULT_EXPR.items()}
# True = 表情图走 AI Core 统一尺寸图；False = 本地 emoji 原图（兜底）
_expr_remote = False


def fetch_expressions() -> bool:
    """从 AI Core 拉取角色的 expressions 映射（含统一尺寸表情图）。

    成功则覆盖本地映射并切换为远端图源；失败保持内置默认兜底。
    """
    global _expr_map, _expr_remote
    try:
        resp = requests.get(
            f"{AI_CORE_URL}/admin/api/personas/{CHARACTER}", timeout=5
        )
        if resp.status_code != 200:
            print(f"[emotion] persona fetch HTTP {resp.status_code}, using local fallback")
            return False
        exprs = (resp.json() or {}).get("expressions") or {}
        m = {}
        for label, v in exprs.items():
            if isinstance(v, dict) and v.get("image"):
                m[label] = {"image": v["image"], "favor": int(v.get("favor", 0) or 0)}
        if not m:
            return False
        _expr_map = m
        _expr_remote = True
        print(f"[emotion] loaded {len(m)} expressions from AI Core ({CHARACTER})")
        return True
    except Exception as e:
        print(f"[emotion] fetch_expressions failed, using local fallback: {e}")
        return False


def _strip_label(text: str) -> str:
    """从 '【{'expression': 'xxx'}】' 整串或纯 label 中取出标签。"""
    m = re.search(r"'expression':\s*'([^']*)'", text)
    label = m.group(1) if m else text
    return label.replace("地", "")


def text_to_emoji(text: str) -> str:
    e = _expr_map.get(_strip_label(text))
    return e["image"] if e else ""


def text_to_favor(text: str) -> int:
    e = _expr_map.get(_strip_label(text))
    return e["favor"] if e else 0


def remove_emotion(message: str) -> str:
    pattern = r"\【\{'expression':\s*'[^']*'\}\】"
    return re.sub(pattern, "", message)


def _emoji_address(image: str) -> str:
    if not image:
        return ""
    if _expr_remote:
        return f"{AI_CORE_URL}/admin/characters/{CHARACTER}/expression/{image}"
    # 本地兜底：保持原有 "{ABS_ROOT}\emoji/xxx.png" 形式
    return f"{root_url}\\emoji/{image}" if root_url else ""


def check_emotion(user_id: str, message: str) -> str:
    """
    检查情绪（在对话中以【{'expression': 'xxx'}】格式表示）
    :param user_id: 用户ID
    :param message: 待处理的消息内容
    :return: 从中提取情绪对应的表情图地址，并进行好感度变化
    """
    pattern = r"\【\{'expression':\s*'[^']*'\}\】"
    matches = re.findall(pattern, message)
    if not matches:
        return ""
    for m in matches:
        favor_change(user_id=user_id, value=text_to_favor(m))
    return _emoji_address(text_to_emoji(matches[0]))
