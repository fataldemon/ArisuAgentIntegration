"""Unified multimodal content normalization.

This module takes any of:

* a plain ``str`` containing legacy placeholders such as
  ``[image,url=...] / [image,file=...] / [image,base64=...]``,
  ``[audio,url=...] / [audio,file=...] / [audio,base64=...]``,
  ``[video,url=... ,fps=2] / [video,file=...] / [video,base64=...]``,
  ``[gif,url=...] / [gif,file=...] / [gif,base64=...]``;
* a list of OpenAI-style content parts
  ``[{"type":"text", "text":"..."}, {"type":"image_url", "image_url":{"url":"..."}}, ...]``;
* a mix of the two (e.g. an OpenAI list whose ``text`` entries still embed
  legacy placeholders);

and produces a flat, ordered list of :class:`ContentPart` objects, then turns
that list into the standard OpenAI ``content`` array expected by the upstream
provider. Order is preserved relative to where each piece appears in the
original input -- this is essential for vision-language models where the
position of an image relative to the surrounding text changes interpretation.

GIFs are converted locally to MP4 (via ffmpeg) and sent as ``video_url``,
since vLLM's video pipeline can process MP4 with proper temporal context.
If ffmpeg is unavailable, GIFs fall back to being sent as raw ``video_url``
or expanded into individual image frames (via Pillow) as a last resort.

When ``prefetch_files=True`` or the provider config has ``prefetch_media=true``,
**HTTP(S) URLs for all media types (image/audio/video) are downloaded locally
and inlined as ``data:`` URIs** before being sent to the upstream. This solves
the problem of vLLM (or other providers) being unable to fetch protected URLs
(e.g. CDN-signed URLs with temporary keys).
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import mimetypes
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

try:
    from PIL import Image, ImageSequence  # type: ignore
except Exception:  # pragma: no cover -- pillow listed in requirements
    Image = None  # type: ignore
    ImageSequence = None  # type: ignore

LOG = logging.getLogger(__name__)

# Placeholder pattern: [type,arg=value,arg=value,...]
# Where type is one of image/audio/video/gif. The value of each arg can be a
# url containing ``,`` or ``]`` characters, so we use a tolerant pattern and
# then split args manually.
_PLACEHOLDER_RE = re.compile(
    r"\[(image|audio|video|gif),(?P<body>[^\[\]]*)\]",
    re.IGNORECASE,
)

# Default frame budget when expanding GIFs. Big GIFs would otherwise blow up
# the prompt; this is the same kind of cap vLLM applies for videos.
DEFAULT_GIF_MAX_FRAMES = 16

# Media cache directory (URL downloads, GIF→MP4 conversions).
_MEDIA_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "media_cache")

# Size-based cleanup thresholds.
_MEDIA_CACHE_MAX_BYTES = 200 * 1024 * 1024   # 200 MiB
_MEDIA_CACHE_KEEP_BYTES = 100 * 1024 * 1024   # 100 MiB
_MEDIA_CLEANUP_INTERVAL = 50                   # check every N writes
_media_cache_write_count = 0


def _media_cache_key(ref: Dict[str, Any]) -> Optional[str]:
    """Compute a deterministic cache key for a media ref."""
    source = ref.get("source")
    if source == "url":
        return hashlib.md5(ref.get("url", "").encode()).hexdigest()
    if source == "file":
        path = ref.get("path", "")
        return hashlib.md5(os.path.abspath(path).encode()).hexdigest()
    if source == "base64":
        data = ref.get("data", "")
        return hashlib.md5(data.encode()).hexdigest()
    return None


def _media_cache_path(key: str, suffix: str = "") -> str:
    os.makedirs(_MEDIA_CACHE_DIR, exist_ok=True)
    return os.path.join(_MEDIA_CACHE_DIR, key + suffix)


def _media_cache_get(key: str, suffix: str = "") -> Optional[bytes]:
    path = _media_cache_path(key, suffix)
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                return f.read()
    except OSError:
        pass
    return None


def _media_cache_put(key: str, data: bytes, suffix: str = "") -> None:
    global _media_cache_write_count
    path = _media_cache_path(key, suffix)
    try:
        with open(path, "wb") as f:
            f.write(data)
        _media_cache_write_count += 1
        if _media_cache_write_count % _MEDIA_CLEANUP_INTERVAL == 0:
            _media_cache_size_cleanup()
    except OSError:
        pass


def _media_cache_size_cleanup() -> None:
    """If total cache exceeds _MEDIA_CACHE_MAX_BYTES, evict oldest files."""
    try:
        entries = []
        total = 0
        for fn in os.listdir(_MEDIA_CACHE_DIR):
            fp = os.path.join(_MEDIA_CACHE_DIR, fn)
            if os.path.isfile(fp):
                sz = os.path.getsize(fp)
                entries.append((os.path.getmtime(fp), sz, fp))
                total += sz
        if total <= _MEDIA_CACHE_MAX_BYTES:
            return
        entries.sort()  # oldest first
        for _mtime, sz, fp in entries:
            try:
                os.unlink(fp)
            except OSError:
                pass
            total -= sz
            if total <= _MEDIA_CACHE_KEEP_BYTES:
                break
        LOG.info("Media cache size cleanup: kept %d bytes", total)
    except Exception:
        pass


def clear_stale_media_cache(max_age_s: float = 86400.0) -> None:
    """Remove cache files older than ``max_age_s`` seconds (default 24 h)."""
    import time
    try:
        if not os.path.isdir(_MEDIA_CACHE_DIR):
            return
        now = time.time()
        removed = 0
        for fn in os.listdir(_MEDIA_CACHE_DIR):
            fp = os.path.join(_MEDIA_CACHE_DIR, fn)
            if os.path.isfile(fp):
                if now - os.path.getmtime(fp) > max_age_s:
                    try:
                        os.unlink(fp)
                        removed += 1
                    except OSError:
                        pass
        if removed:
            LOG.info("Cleared %d stale media cache file(s)", removed)
    except Exception:
        pass


# User-Agent for URL prefetch requests (some CDNs require it).
_PREFETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# URL prefetch helper
# ---------------------------------------------------------------------------


def _prefetch_url(url: str, timeout: float = 15.0) -> Optional[Tuple[bytes, str]]:
    """Download a URL and return ``(raw_bytes, mime_type)``.

    Checks ``media_cache/`` first to avoid repeated CDN downloads.
    Returns ``None`` on any failure (network error, timeout, empty body).
    The caller silently falls back to the original URL when prefetch fails.
    """
    url_key = hashlib.md5(url.encode()).hexdigest()
    data = _media_cache_get(url_key) if url else None
    mime_data = _media_cache_get(url_key, ".mime") if url else None
    if data and mime_data:
        mime = mime_data.decode(errors="replace")
        return data, mime
    try:
        import requests  # lazy import, already in requirements.txt
    except ImportError:
        LOG.warning("requests not available, cannot prefetch %s", url)
        return None
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _PREFETCH_USER_AGENT},
            timeout=timeout,
            stream=True,
        )
        resp.raise_for_status()
        data = resp.content
        if not data:
            return None
        mime = resp.headers.get("Content-Type", "") or _guess_mime_from_url(url)

        # Resize oversized images to avoid blowing up prompt token count.
        mime_root = mime.split(";")[0].strip().lower()
        if Image is not None and mime_root.startswith("image/") and mime_root not in ("image/gif", "image/svg+xml"):
            try:
                img = Image.open(io.BytesIO(data))
                orig_w, orig_h = img.size
                orig_len = len(data)
                max_dim = max(orig_w, orig_h)
                if max_dim > 1024:
                    ratio = 1024.0 / max_dim
                    new_size = (int(orig_w * ratio), int(orig_h * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=85)
                    data = out.getvalue()
                    mime = "image/jpeg"
                    LOG.info(
                        "Resized image %dx%d -> %dx%d (%d -> %d bytes)",
                        orig_w, orig_h, new_size[0], new_size[1],
                        orig_len, len(data),
                    )
            except Exception:
                pass  # if resize fails, keep original

        _media_cache_put(url_key, data)
        _media_cache_put(url_key, mime.encode(), ".mime")
        return data, mime
    except Exception as e:
        LOG.debug("Failed to prefetch %s: %r", url, e)
        return None


def _guess_mime_from_url(url: str) -> str:
    """Guess MIME type from the URL's extension."""
    path = url.split("?")[0].split("#")[0]
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ContentPart:
    """One ordered piece of a normalized message body.

    ``kind`` is one of: ``text``, ``image``, ``audio``, ``video``.
    For media kinds, ``ref`` carries one of:

      * ``{"source": "url",   "url":  "http(s)://..."}``
      * ``{"source": "file",  "path": "/abs/or/rel/path"}``
      * ``{"source": "base64","data": "<b64>", "mime": "image/png"}``

    Extra knobs (such as ``fps`` for videos) are kept in ``options``.
    """

    kind: str
    text: Optional[str] = None
    ref: Optional[Dict[str, Any]] = None
    options: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Placeholder parsing
# ---------------------------------------------------------------------------


def _parse_placeholder_body(body: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse the comma-separated ``key=value`` body of a placeholder.

    Returns a tuple ``(ref, options)`` where ``ref`` contains exactly one of
    ``url`` / ``file`` / ``base64``, and ``options`` is everything else
    (numeric values are coerced when possible).
    """
    # We greedily split on the FIRST '=' of each segment so that the value may
    # itself contain '='. The first segment determines the source kind.
    # However the value may also contain ',' (e.g. base64 padding). To keep
    # things robust we adopt the convention: the source value is whatever
    # follows the first '=' up to the NEXT recognised ``,key=`` boundary, or
    # the end of the body.
    keys = ("url", "file", "base64", "fps", "max_frames", "format", "mime")
    # Find the start indices of every recognised key.
    boundaries: List[Tuple[int, str]] = []
    for key in keys:
        for m in re.finditer(rf"(^|,){key}=", body):
            start = m.start() + (0 if m.start() == 0 else 1)
            boundaries.append((start, key))
    boundaries.sort(key=lambda x: x[0])
    if not boundaries:
        return {}, {}

    pieces: Dict[str, str] = {}
    for i, (start, key) in enumerate(boundaries):
        end = boundaries[i + 1][0] - 1 if i + 1 < len(boundaries) else len(body)
        if end < 0:
            end = len(body)
        # ``body[start:end]`` looks like ``key=value`` (or ``key=value,`` if it
        # was followed by another boundary; the ``-1`` above already stripped
        # the trailing ``,``).
        seg = body[start:end]
        if "=" in seg:
            _, _, val = seg.partition("=")
            pieces[key] = val.strip()

    ref: Dict[str, Any] = {}
    if "url" in pieces:
        ref = {"source": "url", "url": pieces["url"]}
    elif "file" in pieces:
        ref = {"source": "file", "path": pieces["file"]}
    elif "base64" in pieces:
        ref = {
            "source": "base64",
            "data": pieces["base64"],
            "mime": pieces.get("mime", ""),
        }

    options: Dict[str, Any] = {}
    if "fps" in pieces:
        try:
            options["fps"] = float(pieces["fps"])
        except ValueError:
            options["fps"] = pieces["fps"]
    if "max_frames" in pieces:
        try:
            options["max_frames"] = int(pieces["max_frames"])
        except ValueError:
            pass
    if "format" in pieces:
        options["format"] = pieces["format"]
    if "mime" in pieces and "base64" not in pieces:
        options["mime"] = pieces["mime"]
    return ref, options


def _split_text_with_placeholders(text: str) -> List[ContentPart]:
    """Split a string into an ordered list of text / media parts."""
    if not text:
        return []
    parts: List[ContentPart] = []
    last_end = 0
    for m in _PLACEHOLDER_RE.finditer(text):
        if m.start() > last_end:
            parts.append(ContentPart(kind="text", text=text[last_end : m.start()]))
        kind = m.group(1).lower()
        ref, options = _parse_placeholder_body(m.group("body"))
        if not ref:
            # Unrecognised body -- keep it as literal text so we never silently
            # drop user content.
            parts.append(ContentPart(kind="text", text=m.group(0)))
        else:
            # Map ``gif`` to the special expansion kind. The actual frame
            # extraction happens later in :func:`expand_gif_parts`.
            parts.append(
                ContentPart(
                    kind="gif" if kind == "gif" else kind,
                    ref=ref,
                    options=options,
                )
            )
        last_end = m.end()
    if last_end < len(text):
        parts.append(ContentPart(kind="text", text=text[last_end:]))
    return parts


# ---------------------------------------------------------------------------
# OpenAI-array parsing
# ---------------------------------------------------------------------------


def _ref_from_openai_url(url: str) -> Dict[str, Any]:
    if url.startswith("data:"):
        # data:<mime>;base64,<payload>
        head, _, payload = url[len("data:") :].partition(",")
        mime, _, encoding = head.partition(";")
        if encoding == "base64":
            return {"source": "base64", "data": payload, "mime": mime}
        # Non-base64 data URL -- treat the entire URL as opaque.
        return {"source": "url", "url": url}
    if url.startswith(("http://", "https://", "file://")):
        return {"source": "url", "url": url}
    # Bare path -- treat as file.
    return {"source": "file", "path": url}


def _parse_openai_part(part: Dict[str, Any]) -> List[ContentPart]:
    """Convert one OpenAI content part into our internal representation."""
    ptype = part.get("type")
    if ptype == "text":
        # Even within an OpenAI array, the text body may still embed legacy
        # placeholders -- expand them here so order is preserved.
        return _split_text_with_placeholders(part.get("text", "") or "")
    if ptype in ("image_url", "image"):
        url = ""
        if "image_url" in part:
            iu = part["image_url"]
            url = iu["url"] if isinstance(iu, dict) else str(iu)
        elif "image" in part:
            url = str(part["image"])
        if not url:
            return []
        return [ContentPart(kind="image", ref=_ref_from_openai_url(url))]
    if ptype == "input_audio":
        ia = part.get("input_audio", {}) or {}
        data = ia.get("data", "")
        fmt = ia.get("format", "")
        if not data:
            return []
        mime = f"audio/{fmt}" if fmt else "audio/wav"
        return [
            ContentPart(
                kind="audio",
                ref={"source": "base64", "data": data, "mime": mime},
                options={"format": fmt} if fmt else {},
            )
        ]
    if ptype in ("audio_url", "audio"):
        url = part.get("audio_url") or part.get("audio") or ""
        if isinstance(url, dict):
            url = url.get("url", "")
        if not url:
            return []
        return [ContentPart(kind="audio", ref=_ref_from_openai_url(str(url)))]
    if ptype == "video_url":
        vu = part.get("video_url", {}) or {}
        url = vu.get("url") if isinstance(vu, dict) else str(vu)
        if not url:
            return []
        opts: Dict[str, Any] = {}
        if isinstance(vu, dict):
            for k in ("fps", "max_frames"):
                if k in vu:
                    opts[k] = vu[k]
        return [ContentPart(kind="video", ref=_ref_from_openai_url(url), options=opts)]
    if ptype == "video":
        # Either a single URL/path, or a list of frame URLs (Qwen3-VL format).
        val = part.get("video")
        if isinstance(val, list):
            out: List[ContentPart] = []
            for u in val:
                if not u:
                    continue
                out.append(ContentPart(kind="image", ref=_ref_from_openai_url(str(u))))
            return out
        if isinstance(val, str):
            return [ContentPart(kind="video", ref=_ref_from_openai_url(val))]
        return []
    # Unknown types are dropped silently rather than aborting the request.
    return []


# ---------------------------------------------------------------------------
# Public API: normalize
# ---------------------------------------------------------------------------


def normalize_content(content: Any) -> List[ContentPart]:
    """Normalize a message ``content`` into an ordered :class:`ContentPart` list.

    Accepts ``None`` / ``""`` (returns an empty list), a plain string, an
    OpenAI-style list of parts, or a mix.
    """
    if content is None:
        return []
    if isinstance(content, str):
        return _split_text_with_placeholders(content)
    if isinstance(content, list):
        out: List[ContentPart] = []
        for part in content:
            if isinstance(part, str):
                out.extend(_split_text_with_placeholders(part))
            elif isinstance(part, dict):
                out.extend(_parse_openai_part(part))
        return out
    # Fallback: coerce to string.
    return _split_text_with_placeholders(str(content))


# ---------------------------------------------------------------------------
# GIF expansion (the only piece we must process locally because vLLM does not
# treat .gif as a video container).
# ---------------------------------------------------------------------------


def _load_bytes_from_ref(ref: Dict[str, Any]) -> Optional[bytes]:
    """Best-effort loader for a media ``ref`` -- returns ``None`` on failure."""
    if not ref:
        return None
    source = ref.get("source")
    if source == "base64":
        try:
            return base64.b64decode(ref.get("data", ""))
        except Exception:
            return None
    if source == "file":
        path = ref.get("path", "")
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None
    if source == "url":
        url = ref.get("url", "")
        if not url:
            return None
        # Local file:// URL is OK to read directly.
        if url.startswith("file://"):
            path = url[len("file://") :]
            try:
                with open(path, "rb") as f:
                    return f.read()
            except OSError:
                return None
        # For http(s) URLs we deliberately do not fetch -- caller decides via
        # ``prefetch_media``.
        return None
    return None


def _expand_gif(part: ContentPart) -> List[ContentPart]:
    """Expand one GIF :class:`ContentPart` into a sequence of image parts."""
    if Image is None or ImageSequence is None:
        # Pillow unavailable -- treat the GIF as a regular image reference.
        return [ContentPart(kind="image", ref=part.ref, options=part.options)]
    data = _load_bytes_from_ref(part.ref or {})
    if data is None:
        # For URLs we do not fetch; just hand the GIF to the model as-is.
        return [ContentPart(kind="image", ref=part.ref, options=part.options)]
    try:
        img = Image.open(io.BytesIO(data))
        frames: List[Image.Image] = []
        for f in ImageSequence.Iterator(img):
            frames.append(f.convert("RGBA").copy())
    except Exception:
        return [ContentPart(kind="image", ref=part.ref, options=part.options)]

    if not frames:
        return [ContentPart(kind="image", ref=part.ref, options=part.options)]

    max_frames = int(part.options.get("max_frames", DEFAULT_GIF_MAX_FRAMES) or DEFAULT_GIF_MAX_FRAMES)
    fps = part.options.get("fps")
    if fps:
        try:
            fps_f = float(fps)
            duration_ms = int(img.info.get("duration", 100)) or 100
            stride = max(1, int(round(1000.0 / fps_f / duration_ms)))
            frames = frames[::stride]
        except Exception:
            pass
    if len(frames) > max_frames:
        # Uniformly subsample down to ``max_frames``.
        step = len(frames) / float(max_frames)
        sampled = [frames[int(i * step)] for i in range(max_frames)]
        frames = sampled

    out: List[ContentPart] = []
    for frame in frames:
        buf = io.BytesIO()
        frame.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        out.append(
            ContentPart(
                kind="image",
                ref={"source": "base64", "data": b64, "mime": "image/png"},
            )
        )
    return out


def expand_gif_parts(parts: Iterable[ContentPart]) -> List[ContentPart]:
    """Expand every ``gif`` part to ``image`` frames; keep others unchanged."""
    out: List[ContentPart] = []
    for p in parts:
        if p.kind == "gif":
            out.extend(_expand_gif(p))
        else:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Serialization to OpenAI content array
# ---------------------------------------------------------------------------


def _guess_mime_from_path(path: str, fallback: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or fallback


def _read_gif_fps(gif_bytes: bytes) -> float:
    """Extract playback frame-rate from GIF bytes using Pillow."""
    from io import BytesIO
    img = Image.open(BytesIO(gif_bytes))
    n_frames = getattr(img, "n_frames", 1)
    if n_frames <= 1:
        return 10.0
    frame_ms = img.info.get("duration", 100) or 100
    if frame_ms <= 0:
        frame_ms = 100
    return 1000.0 / max(frame_ms, 1)


def _gif_bytes_to_mp4(gif_bytes: bytes, fps: int = 2) -> Optional[bytes]:
    """Convert GIF bytes to MP4 via ffmpeg. Returns None if unavailable/error."""
    import subprocess
    import tempfile
    try:
        real_fps = _read_gif_fps(gif_bytes)
        effective_fps = max(min(int(real_fps + 0.5), 10), 3)
    except Exception:
        effective_fps = fps
    LOG.info("GIF → MP4 converting: %d bytes, fps=%d (effective=%d)",
             len(gif_bytes), fps, effective_fps)
    # Determine total frames and duration to decide whether looping is needed.
    try:
        from io import BytesIO
        img = Image.open(BytesIO(gif_bytes))
        _n_frames = getattr(img, "n_frames", 1)
        _frame_ms = img.info.get("duration", 100) or 100
        if _frame_ms <= 0:
            _frame_ms = 100
        _total_duration = _n_frames * _frame_ms / 1000.0
    except Exception:
        _n_frames, _total_duration = 1, 0.1
    _effective_frames = max(1, int(_total_duration * effective_fps))
    gif_path = None
    mp4_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            f.write(gif_bytes)
            gif_path = f.name
        mp4_path = gif_path + ".mp4"
        # Build ffmpeg command based on whether the GIF has enough frames.
        cmd = ["ffmpeg", "-y"]
        if _effective_frames < 3:
            loop = int(3.0 / max(_total_duration, 0.1))
            cmd += ["-stream_loop", str(loop), "-i", gif_path,
                    "-vf", f"fps={effective_fps},scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", "mpeg4", "-q:v", "2",
                    "-pix_fmt", "yuv420p", "-movflags", "faststart",
                    "-an",
                    "-frames:v", "3",
                    mp4_path]
        else:
            cmd += ["-i", gif_path,
                    "-vf", f"fps={effective_fps},scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", "mpeg4", "-q:v", "2",
                    "-pix_fmt", "yuv420p", "-movflags", "faststart",
                    "-an",
                    mp4_path]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 0:
            with open(mp4_path, "rb") as f:
                mp4_bytes = f.read()
            LOG.info("GIF → MP4 done: %d → %d bytes", len(gif_bytes), len(mp4_bytes))
            return mp4_bytes
        LOG.warning("ffmpeg failed (rc=%d): %s",
                    result.returncode,
                    result.stderr.decode(errors="replace")[-800:])
    except Exception as e:
        LOG.warning("GIF → MP4 conversion failed: %r", e)
    finally:
        for p in (gif_path, mp4_path):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass
    return None


def _get_gif_bytes(ref: Dict[str, Any]) -> Optional[bytes]:
    """Extract raw GIF bytes from any ref type (file, base64, url)."""
    source = ref.get("source")
    if source == "base64":
        data = ref.get("data", "")
        try:
            result = base64.b64decode(data)
            LOG.info("GIF bytes from base64: %d bytes", len(result))
            return result
        except Exception:
            LOG.info("GIF base64 decode failed: %r", ref.get("mime", "?"))
            return None
    if source == "file":
        path = ref.get("path", "")
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    result = f.read()
                LOG.info("GIF bytes from file: %s → %d bytes", path, len(result))
                return result
            except OSError as e:
                LOG.info("GIF file read failed: %s → %r", path, e)
    if source == "url":
        url = ref.get("url", "")
        if url.startswith(("http://", "https://")):
            LOG.info("GIF prefetching URL: %s", url)
            result = _prefetch_url(url)
            if result is not None:
                data, mime = result
                LOG.info("GIF bytes from URL: %d bytes, mime=%s", len(data), mime)
                return data
            LOG.info("GIF URL prefetch failed: %s", url)
    LOG.info("No GIF bytes from ref: source=%s", source)
    return None


def _ref_to_openai_url(
    ref: Dict[str, Any],
    *,
    fallback_mime: str,
    prefetch: bool = False,
) -> Optional[str]:
    """Turn a ``ref`` into the URL string used by OpenAI-style content parts.

    When ``prefetch`` is true, ``file`` refs are inlined as base64 data URLs,
    and **HTTP(S) URLs are downloaded and inlined** so that the upstream
    provider does not need to fetch them itself (solving CDN auth issues).
    ``url`` refs are NEVER fetched here -- the caller may pre-process them.
    """
    source = ref.get("source")
    if source == "url":
        url = str(ref.get("url", ""))
        if prefetch and url.startswith(("http://", "https://")):
            result = _prefetch_url(url)
            if result is not None:
                data, mime = result
                b64 = base64.b64encode(data).decode("ascii")
                return f"data:{mime};base64,{b64}"
            # Prefetch failed -- fall back to the original URL so the request
            # doesn't completely fail; vLLM may still be able to fetch it.
            LOG.debug("Prefetch failed for %s, falling back to raw URL", url)
        return None
    if source == "file":
        path = ref.get("path", "")
        if prefetch and path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                mime = _guess_mime_from_path(path, fallback_mime)
                b64 = base64.b64encode(raw).decode("ascii")
                return f"data:{mime};base64,{b64}"
            except OSError:
                pass
        # Conform to RFC 8089 (file://) so the remote server can read it.
        if path.startswith("/"):
            return f"file://{path}"
        return f"file://{os.path.abspath(path)}"
    if source == "base64":
        mime = ref.get("mime") or fallback_mime
        return f"data:{mime};base64,{ref.get('data','')}"
    return ""


def _looks_like_gif(part: ContentPart) -> bool:
    """Return True if the ContentPart likely refers to a GIF image."""
    ref = part.ref or {}
    source = ref.get("source")
    if source == "url":
        url = ref.get("url", "")
        path = url.split("?")[0].split("#")[0]
        if path.lower().endswith(".gif"):
            return True
        # CDN URL without .gif suffix — check in-memory cache first.
        key = _media_cache_key(ref)
        if key and _media_cache_get(key, ".mp4") is not None:
            LOG.info("Detected GIF via cache hit: %s", url[:80])
            return True
        # Download header bytes to detect GIF magic number.
        if url.startswith(("http://", "https://")):
            result = _prefetch_url(url)
            if result is not None:
                return result[0][:6] in (b"GIF87a", b"GIF89a")
        return False
    if source == "file":
        path = ref.get("path", "")
        return path.lower().endswith(".gif")
    if source == "base64":
        data = ref.get("data", "")
        try:
            raw = base64.b64decode(data[:64])   # 只解码前 64 字符
            return raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a")
        except Exception:
            return False
    return False


def to_openai_content(
    parts: Iterable[ContentPart],
    *,
    prefetch_files: bool = False,
    fallback_text: str = "[media unavailable]",
) -> Union[str, List[Dict[str, Any]]]:
    """Serialize an ordered :class:`ContentPart` list to an OpenAI content payload.

    If the list contains only text parts, returns a single concatenated string
    (compatible with text-only providers). Otherwise returns the canonical
    OpenAI list-of-parts form.
    """
    parts = list(parts)
    if not parts:
        return ""
    if all(p.kind == "text" for p in parts):
        return "".join(p.text or "" for p in parts)

    out: List[Dict[str, Any]] = []
    for p in parts:
        if p.kind == "text":
            out.append({"type": "text", "text": p.text or ""})
        elif p.kind == "image":
            if _looks_like_gif(p):
                LOG.info("Detected GIF via _looks_like_gif: source=%s", (p.ref or {}).get("source", "?"))
                fps = int(p.options.get("fps", 2))
                key = _media_cache_key(p.ref or {})
                mp4_bytes = _media_cache_get(key, ".mp4") if key else None
                if mp4_bytes:
                    LOG.info("GIF cache hit: %s (%d bytes)", key, len(mp4_bytes))
                else:
                    gif_bytes = _get_gif_bytes(p.ref or {})
                    if gif_bytes:
                        mp4_bytes = _gif_bytes_to_mp4(gif_bytes, fps=fps)
                        if mp4_bytes and key:
                            _media_cache_put(key, mp4_bytes, ".mp4")
                    else:
                        mp4_bytes = None
                if mp4_bytes:
                    b64 = base64.b64encode(mp4_bytes).decode("ascii")
                    url = f"data:video/mp4;base64,{b64}"
                else:
                    LOG.info("GIF → MP4 failed, falling back to raw video_url")
                    url = _ref_to_openai_url(
                        p.ref or {}, fallback_mime="video/mp4", prefetch=prefetch_files
                    )
                if url is None:
                    if fallback_text:
                        out.append({"type": "text", "text": fallback_text})
                    continue
                video_part = {"type": "video_url", "video_url": {"url": url}}
                for k in ("max_frames", "fps"):
                    if k in p.options:
                        video_part["video_url"][k] = p.options[k]
                out.append(video_part)
            else:
                # 普通图片
                url = _ref_to_openai_url(
                    p.ref or {}, fallback_mime="image/png", prefetch=prefetch_files
                )
                if url is None:
                    if fallback_text:
                        out.append({"type": "text", "text": fallback_text})
                    continue
                out.append({"type": "image_url", "image_url": {"url": url}})
        elif p.kind == "audio":
            # 同样需要处理 url is None 的情况
            ref = p.ref or {}
            if ref.get("source") == "base64":
                mime = ref.get("mime") or "audio/wav"
                fmt = mime.split("/", 1)[-1] if "/" in mime else (p.options.get("format") or "wav")
                out.append({
                    "type": "input_audio",
                    "input_audio": {"data": ref.get("data", ""), "format": fmt},
                })
            else:
                url = _ref_to_openai_url(
                    ref, fallback_mime="audio/wav", prefetch=prefetch_files
                )
                if url is None:
                    if fallback_text:
                        out.append({"type": "text", "text": fallback_text})
                    continue
                out.append({"type": "audio_url", "audio_url": {"url": url}})
        elif p.kind == "video":
            ref = p.ref or {}
            url = _ref_to_openai_url(
                ref, fallback_mime="video/mp4", prefetch=prefetch_files
            )
            if url is None:
                if fallback_text:
                    out.append({"type": "text", "text": fallback_text})
                continue
            video_part = {"type": "video_url", "video_url": {"url": url}}
            for k in ("fps", "max_frames"):
                if k in p.options:
                    video_part["video_url"][k] = p.options[k]
            out.append(video_part)
        elif p.kind == "gif":
            LOG.info("GIF part (kind=gif): source=%s, fps=%d",
                     (p.ref or {}).get("source", "?"),
                     int(p.options.get("fps", 2)))
            fps = int(p.options.get("fps", 2))
            key = _media_cache_key(p.ref or {})
            mp4_bytes = _media_cache_get(key, ".mp4") if key else None
            if mp4_bytes:
                LOG.info("GIF cache hit: %s (%d bytes)", key, len(mp4_bytes))
            else:
                gif_bytes = _get_gif_bytes(p.ref or {})
                if gif_bytes:
                    mp4_bytes = _gif_bytes_to_mp4(gif_bytes, fps=fps)
                    if mp4_bytes and key:
                        _media_cache_put(key, mp4_bytes, ".mp4")
                else:
                    mp4_bytes = None
            if mp4_bytes:
                b64 = base64.b64encode(mp4_bytes).decode("ascii")
                url = f"data:video/mp4;base64,{b64}"
            else:
                LOG.info("GIF → MP4 failed, falling back to raw video_url")
                url = _ref_to_openai_url(
                    p.ref or {}, fallback_mime="video/mp4", prefetch=prefetch_files
                )
            if url is None:
                if fallback_text:
                    out.append({"type": "text", "text": fallback_text})
                continue
            video_part = {"type": "video_url", "video_url": {"url": url}}
            for k in ("max_frames", "fps"):
                if k in p.options:
                    video_part["video_url"][k] = p.options[k]
            out.append(video_part)
    return out


def normalize_message_content(
    content: Any,
    *,
    expand_gifs: bool = True,
    prefetch_files: bool = False,
) -> Union[str, List[Dict[str, Any]]]:
    """End-to-end helper: normalize -> expand GIFs -> serialize.

    This is the function chat code should call. Returns either a plain
    string (when no multimedia is present) or an OpenAI content array.
    """
    parts = normalize_content(content)
    if expand_gifs:
        parts = expand_gif_parts(parts)
    return to_openai_content(parts, prefetch_files=prefetch_files)


def has_media(parts_or_content: Any) -> bool:
    """Whether the normalized content contains any non-text part."""
    if isinstance(parts_or_content, list) and parts_or_content and isinstance(
        parts_or_content[0], ContentPart
    ):
        return any(p.kind != "text" for p in parts_or_content)
    parts = normalize_content(parts_or_content)
    return any(p.kind != "text" for p in parts)