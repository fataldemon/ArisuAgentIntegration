"""Character expression-image handling.

Expressions (the `【{'expression':'xxx'}】` markers a character emits) map to
small emoji images that are now first-class character assets shared by every
channel (QQ bot, Chat web page). The label -> {image, favor_delta} mapping
lives in ``persona.json`` (under the ``expressions`` key, parked in
``Persona.extra``); the image files live under::

    embedding/<character>/expression/image/<file>.png

All images are normalised to a single max edge length on the way in (upload
or one-shot preprocessing) so they render at a consistent size everywhere.
"""

from __future__ import annotations

import io
import os
from typing import Optional

from PIL import Image

_EMBEDDING_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "embedding"
)

DEFAULT_MAX_SIZE = 480


def expression_image_dir(character: str) -> str:
    return os.path.join(_EMBEDDING_ROOT, character, "expression", "image")


def expression_image_path(character: str, filename: str) -> str:
    return os.path.join(expression_image_dir(character), os.path.basename(filename))


def expression_image_url(character: str, filename: str) -> str:
    """Public URL the Chat frontend / QQ bot use to fetch the image."""
    return f"/admin/characters/{character}/expression/{os.path.basename(filename)}"


def _resize_keep_ratio(img: Image.Image, max_size: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= 0:
        return img
    scale = max_size / float(longest)
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return img.resize(new_size, Image.LANCZOS)


def normalize_image_bytes(data: bytes, max_size: int = DEFAULT_MAX_SIZE) -> bytes:
    """Resize raw image bytes to ``max_size`` (longest edge), return PNG bytes."""
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    img = _resize_keep_ratio(img, max_size)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def save_expression_image(
    character: str, filename: str, data: bytes, max_size: int = DEFAULT_MAX_SIZE
) -> str:
    """Normalise ``data`` and write it under the character's expression dir.

    Returns the saved file's basename (always a ``.png``).
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    out_name = f"{stem}.png"
    dst_dir = expression_image_dir(character)
    os.makedirs(dst_dir, exist_ok=True)
    png = normalize_image_bytes(data, max_size)
    with open(os.path.join(dst_dir, out_name), "wb") as f:
        f.write(png)
    return out_name


def preprocess_dir(
    character: str, src_dir: str, max_size: int = DEFAULT_MAX_SIZE
) -> list[str]:
    """One-shot: normalise every PNG/JPG in ``src_dir`` into the character's
    expression image dir. Returns the list of output filenames.
    """
    out: list[str] = []
    for name in sorted(os.listdir(src_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        with open(os.path.join(src_dir, name), "rb") as f:
            data = f.read()
        out.append(save_expression_image(character, name, data, max_size))
    return out
