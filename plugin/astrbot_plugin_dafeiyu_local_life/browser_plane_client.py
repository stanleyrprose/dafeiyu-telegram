"""Owner-only /read transport to the Mac Browser Plane one-shot file bridge.

This component never browses directly and never falls back to unreviewed HTTP.
The host broker must be provisioned separately; a missing broker fails closed.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .web_read import _public_target


class BrowserPlaneReadError(RuntimeError):
    """Sanitized user-facing browser transport failure."""


_URL_TOKEN = re.compile(r"https://[^\s<>\"'`，。！？；：、（）【】《》]+", re.IGNORECASE)
_TRAILING_SENTENCE_PUNCTUATION = ".,!?;:)]}”’"


def extract_read_url(message: str) -> str:
    """Pick one HTTPS URL, excluding accompanying /read instructions.

    /read takes a GreedyStr, so the user's prose must never become part of the
    URL forwarded to the Mac Browser Plane.
    """
    if not isinstance(message, str) or len(message) > 6000:
        raise BrowserPlaneReadError("请提供一个 HTTPS 网页链接。")
    candidates = _URL_TOKEN.findall(message)
    if len(candidates) != 1:
        raise BrowserPlaneReadError("请一次提供一个 HTTPS 网页链接，不要包含多个网址。")
    target = candidates[0].rstrip(_TRAILING_SENTENCE_PUNCTUATION)
    if not 9 < len(target) <= 2048:
        raise BrowserPlaneReadError("HTTPS 网页链接无效或过长。")
    return target


def _requires_cloudflare_access_login(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return host.endswith(".cloudflareaccess.com") or parsed.path.startswith("/cdn-cgi/access/")


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_name("." + path.name + ".tmp")
    encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def acquire_public_page(url: str, *, timeout_sec: float = 100.0) -> tuple[str, str, str]:
    """Request a bounded public-page acquisition using host-side browser_acquire.

    Returns final_url, extracted_text, engine. No authenticated profiles,
    C2/C3 interactions, local file reads or arbitrary tool names are accepted.
    """
    if os.getenv("DAFEIYU_BROWSER_PLANE_ENABLED", "false").lower() != "true":
        raise BrowserPlaneReadError("Mac Browser Plane 尚未启用，无法读取网页")
    target = url.strip()
    try:
        _public_target(target)
    except (ValueError, OSError) as exc:
        raise BrowserPlaneReadError("只能读取可解析的公开 HTTPS 网页") from exc

    root = Path(os.getenv("DAFEIYU_BROWSER_PLANE_DIR", "/AstrBot/browser-plane-bridge"))
    requests = root / "requests"
    responses = root / "responses"
    if any(p.is_symlink() or not p.is_dir() for p in (root, requests, responses)):
        raise BrowserPlaneReadError("Mac Browser Plane 本机桥接未就绪")

    request_id = uuid.uuid4().hex
    request_path = requests / (request_id + ".json")
    response_path = responses / (request_id + ".json")
    lifetime = max(5.0, min(float(timeout_sec), 110.0))
    deadline = time.monotonic() + lifetime
    request = {
        "version": 1,
        "id": request_id,
        "url": target,
        "created_at": time.time(),
        "expires_at": time.time() + lifetime,
    }
    try:
        _atomic_json(request_path, request)
        while time.monotonic() < deadline:
            if response_path.is_file() and not response_path.is_symlink():
                try:
                    if response_path.stat().st_size > 48000:
                        raise ValueError("oversized response")
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError) as exc:
                    raise BrowserPlaneReadError("Mac Browser Plane 返回内容无效") from exc
                if not isinstance(response, dict) or response.get("id") != request_id:
                    raise BrowserPlaneReadError("Mac Browser Plane 回执标识不一致")
                if response.get("ok") is not True:
                    raise BrowserPlaneReadError(
                        str(response.get("error") or "Mac Browser Plane 网页读取失败")[:180]
                    )
                final_url, content, engine = (
                    response.get("url"), response.get("text"), response.get("engine")
                )
                if not all(isinstance(x, str) for x in (final_url, content, engine)):
                    raise BrowserPlaneReadError("Mac Browser Plane 回执缺少正文")
                if _requires_cloudflare_access_login(final_url):
                    raise BrowserPlaneReadError("目标网站需要 Cloudflare Access 登录，当前只能读取公开网页。")
                try:
                    _public_target(final_url)
                except (ValueError, OSError) as exc:
                    raise BrowserPlaneReadError("Mac Browser Plane 回执包含非公开目标") from exc
                return final_url, content[:9000], engine[:60]
            time.sleep(0.3)
        raise BrowserPlaneReadError("Mac Browser Plane 请求超时；未使用其他网页通道")
    finally:
        request_path.unlink(missing_ok=True)
        response_path.unlink(missing_ok=True)
