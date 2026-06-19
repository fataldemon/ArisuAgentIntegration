import os
import re
from src.dao.user import favor_change
from dotenv import load_dotenv

load_dotenv()
root_url = os.environ.get("ABS_ROOT")

emotion_dict = {
    "【{'expression': '认真'}】": ("emoji/angry.png", 0),
    "【{'expression': '坚定'}】": ("emoji/angry.png", 0),
    "【{'expression': '承诺'}】": ("emoji/angry.png", 0),
    "【{'expression': '生气'}】": ("emoji/angry.png", -5),
    "【{'expression': '急切'}】": ("emoji/angry.png", 0),
    "【{'expression': '烦恼'}】": ("emoji/screwup.png", 0),
    "【{'expression': '专注'}】": ("emoji/awake.png", 0),
    "【{'expression': '诚实'}】": ("emoji/awake.png", 0),
    "【{'expression': '期待'}】": ("emoji/smile.png", 1),
    "【{'expression': '回答'}】": ("emoji/awake.png", 0),
    "【{'expression': '回忆'}】": ("emoji/thinking.png", 0),
    "【{'expression': '发愣'}】": ("emoji/awake.png", 0),
    "【{'expression': '察觉'}】": ("emoji/awake.png", 0),
    "【{'expression': '建议'}】": ("emoji/smile.png", 0),
    "【{'expression': '好奇'}】": ("emoji/awake.png", 1),
    "【{'expression': '自信'}】": ("emoji/confident.png", 0),
    "【{'expression': '自豪'}】": ("emoji/confident.png", 0),
    "【{'expression': '解释'}】": ("emoji/smile.png", 0),
    "【{'expression': '失望'}】": ("emoji/awkward.png", -1),
    "【{'expression': '委屈'}】": ("emoji/cry.png", -2),
    "【{'expression': '伤心'}】": ("emoji/cry.png", -3),
    "【{'expression': '高兴'}】": ("emoji/smile.png", 1),
    "【{'expression': '开心'}】": ("emoji/happy.png", 2),
    "【{'expression': '欢迎'}】": ("emoji/smile.png", 1),
    "【{'expression': '崇拜'}】": ("emoji/smile.png", 2),
    "【{'expression': '愉快'}】": ("emoji/smile.png", 1),
    "【{'expression': '贴心'}】": ("emoji/smile.png", 1),
    "【{'expression': '赞同'}】": ("emoji/smile.png", 1),
    "【{'expression': '邀请'}】": ("emoji/smile.png", 0),
    "【{'expression': '兴奋'}】": ("emoji/happy.png", 2),
    "【{'expression': '快乐'}】": ("emoji/happy.png", 1),
    "【{'expression': '难过'}】": ("emoji/awkward.png", -1),
    "【{'expression': '为难'}】": ("emoji/awkward.png", 0),
    "【{'expression': '紧张'}】": ("emoji/awkward.png", 0),
    "【{'expression': '困惑'}】": ("emoji/awkward.png", 0),
    "【{'expression': '困扰'}】": ("emoji/awkward.png", -1),
    "【{'expression': '疑惑'}】": ("emoji/awkward.png", 0),
    "【{'expression': '害怕'}】": ("emoji/sweating.png", -2),
    "【{'expression': '无奈'}】": ("emoji/sweating.png", -1),
    "【{'expression': '平和'}】": ("emoji/plain.png", 0),
    "【{'expression': '无聊'}】": ("emoji/plain.png", 0),
    "【{'expression': '慌张'}】": ("emoji/screwup.png", 0),
    "【{'expression': '害羞'}】": ("emoji/shy.png", 0),
    "【{'expression': '羞涩'}】": ("emoji/shy.png", 0),
    "【{'expression': '微笑'}】": ("emoji/confident.png", 0),
    "【{'expression': '惊喜'}】": ("emoji/smile.png", 2),
    "【{'expression': '理解'}】": ("emoji/smile.png", 0),
    "【{'expression': '喜悦'}】": ("emoji/smile.png", 1),
    "【{'expression': '担忧'}】": ("emoji/sweating.png", 0),
    "【{'expression': '流汗'}】": ("emoji/sweating.png", 0),
    "【{'expression': '尴尬'}】": ("emoji/sweating.png", -1),
    "【{'expression': '犹豫'}】": ("emoji/awkward.png", 0),
    "【{'expression': '震惊'}】": ("emoji/sweating.png", 0),
    "【{'expression': '惊讶'}】": ("emoji/sweating.png", 0),
    "【{'expression': '思考'}】": ("emoji/thinking.png", 0),
    "【{'expression': '沉思'}】": ("emoji/thinking.png", 0),
    "【{'expression': '否认'}】": ("emoji/thinking.png", 0),
    "【{'expression': '睡觉'}】": ("emoji/thinking.png", 0),
    "【{'expression': '陈述'}】": ("emoji/plain.png", 0),
    "【{'expression': '祈祷'}】": ("emoji/thinking.png", 1),
    "【{'expression': '拒绝'}】": ("emoji/angry.png", -1),
    "【{'expression': '警惕'}】": ("emoji/angry.png", -1),
    "【{'expression': '感动'}】": ("emoji/touching.png", 2),
    "【{'expression': '感激'}】": ("emoji/touching.png", 2),
    "【{'expression': '道歉'}】": ("emoji/sweating.png", 1),
    "【{'expression': '可爱'}】": ("emoji/happy.png", 1),
    "【{'expression': '俏皮'}】": ("emoji/happy.png", 1),
    "【{'expression': '调皮'}】": ("emoji/happy.png", 1),
    "【{'expression': '卖萌'}】": ("emoji/happy.png", 1),
    "【{'expression': '眨眼'}】": ("emoji/happy.png", 1)
}


def text_to_emoji(text: str) -> str:
    text = text.replace("地", "")
    result = emotion_dict.get(text)
    if result is not None:
        return result[0]
    return ""


def text_to_favor(text: str) -> int:
    text = text.replace("地", "")
    result = emotion_dict.get(text)
    if result is not None:
        return result[1]
    return 0


def remove_emotion(message: str) -> str:
    pattern = r"\【\{'expression':\s*'[^']*'\}\】"
    return re.sub(pattern, "", message)


def check_emotion(user_id: str, message: str) -> str:
    """
    检查情绪（在对话中以【{'expression': 'xxx'}】格式表示）
    :param user_id: 用户ID
    :param message: 待处理的消息内容
    :return: 从中提取情绪对应的表情，并进行好感度变化
    """
    pattern = r"\【\{'expression':\s*'[^']*'\}\】"
    matches = re.findall(pattern, message)
    if not matches:
        return ""
    for m in matches:
        favor = text_to_favor(m)
        favor_change(user_id=user_id, value=favor)
    emoji = text_to_emoji(matches[0])
    return f"{root_url}\{emoji}" if emoji else ""
