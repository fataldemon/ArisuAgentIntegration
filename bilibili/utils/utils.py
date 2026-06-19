import base64
import re


def remove_emotion(message: str) -> str:
    pattern = r'\【[^\】^\]]*[\]\】]'
    match = re.findall(pattern, message)
    if not len(match) == 0:
        return message.replace(match[0], "")
    else:
        return message


def get_image_as_data_uri(image_path):
    with open(image_path, "rb") as img_file:
        data = img_file.read()
    encoded = base64.b64encode(data).decode("utf-8")
    # 假设图片为 PNG 格式，如是 JPEG 则修改 mime 类型为 image/jpeg
    return f"data:image/png;base64,{encoded}"
