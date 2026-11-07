#!/usr/bin/env python3
"""One-shot host-only broker for the existing Mac Browser Plane stdio MCP.

Triggered by launchd QueueDirectories; no HTTP port, new Browser worker,
credential forwarding, generic tool dispatch, or browser profile access.
"""
from __future__ import annotations

import fcntl
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

from browser_plane.config import RuntimePaths

ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_ARTIFACT = 1_500_000
MAX_RESULT_CHARS = 9000
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
IGNORED = {"script", "style", "noscript", "svg", "nav", "footer", "form", "head"}


class ReadRejected(ValueError):
    pass


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.blocks: list[str] = []
        self.buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in IGNORED:
            self._flush()
            self.ignored += 1
        elif tag in {"p", "h1", "h2", "h3", "h4", "li", "article", "br", "title", "section"}:
            self._flush()

    def handle_endtag(self, tag):
        if tag in IGNORED:
            self.ignored = max(0, self.ignored - 1)
        elif tag in {"p", "h1", "h2", "h3", "h4", "li", "article", "section"}:
            self._flush()

    def handle_data(self, data):
        if not self.ignored and len(self.blocks) < 350:
            self.buffer.append(data)

    def _flush(self):
        if self.buffer:
            value = re.sub(r"\s+", " ", " ".join(self.buffer)).strip()
            if value and len(value) > 2:
                self.blocks.append(value)
        self.buffer.clear()

    def text(self):
        self._flush()
        return "\n".join(self.blocks)[:MAX_RESULT_CHARS]


def _public_https(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ReadRejected("URL 无效")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)):
        raise ReadRejected("仅允许公开 HTTPS 页面")
    host = parsed.hostname.lower().rstrip(".")
    if not host or "." not in host or host.endswith((".local", ".internal", ".localhost", ".test", ".invalid")):
        raise ReadRejected("禁止访问本地或内部主机")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ReadRejected("禁止直接访问 IP")
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ReadRejected("域名无法解析") from exc
    if not records or any(not ipaddress.ip_address(item[4][0]).is_global for item in records):
        raise ReadRejected("目标不是公开互联网地址")
    return url


def _atomic_response(path: Path, response: dict) -> None:
    data = (json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > 48000:
        raise ReadRejected("响应过长")
    tmp = path.with_name("." + path.name + "." + secrets.token_hex(6) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_artifact(result: dict, job_id: str) -> str:
    raw_path = result.get("artifact_path")
    if not isinstance(raw_path, str) or not raw_path:
        excerpt = result.get("text_excerpt")
        if isinstance(excerpt, str) and excerpt.strip():
            return excerpt[:MAX_RESULT_CHARS]
        raise ReadRejected("Browser Plane 没有返回可读取的页面正文")

    evidence = RuntimePaths.discover().evidence_dir.resolve(strict=True)
    artifact = Path(raw_path)
    if artifact.is_symlink() or not artifact.is_file():
        raise ReadRejected("Browser Plane 证据文件无效")
    canonical = artifact.resolve(strict=True)
    if not canonical.is_relative_to(evidence) or canonical.parent.name != job_id:
        raise ReadRejected("Browser Plane 证据路径不属于当前任务")
    if not stat.S_ISREG(canonical.stat().st_mode) or canonical.stat().st_size > MAX_ARTIFACT:
        raise ReadRejected("网页证据体积超限")
    body = canonical.read_bytes()
    if not isinstance(result.get("sha256"), str) or hashlib.sha256(body).hexdigest() != result["sha256"]:
        raise ReadRejected("网页证据校验失败")

    kind = str(result.get("content_type") or "").split(";", 1)[0].strip().lower()
    if kind not in ALLOWED_CONTENT_TYPES:
        raise ReadRejected("该链接不是可读取的 HTML 或纯文本网页")

    charset = "utf-8"
    match = re.search(r"charset\s*=\s*['\"]?([\w-]+)", str(result.get("content_type") or ""), re.I)
    if match:
        charset = match.group(1)
    try:
        decoded = body.decode(charset, errors="replace")
    except LookupError:
        decoded = body.decode("utf-8", errors="replace")
    if kind == "text/plain":
        return decoded[:MAX_RESULT_CHARS]
    parser = PageText()
    parser.feed(decoded)
    return parser.text()


def _acquire(url: str, command: Path) -> dict:
    args = {
        "url": url,
        "queue_timeout_sec": 12,
        "fetch_max_run_sec": 25,
        "render_max_run_sec": 45,
        "client_timeout_sec": 85,
    }
    # Invoke only the reviewed read-only Browser Plane capability.
    proc = subprocess.Popen(
        [str(command), "call", "browser_acquire", "--args-json",
         json.dumps(args, ensure_ascii=False, separators=(",", ":"))],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=96)
    except subprocess.TimeoutExpired as exc:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise ReadRejected("Mac Browser Plane 调用超时") from exc
    if proc.returncode or len(output) > 80000:
        raise ReadRejected("Mac Browser Plane 调用失败")
    payload = json.loads(output)
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ReadRejected("Mac Browser Plane 未完成任务")
    selected = payload.get("structured_content")
    if not isinstance(selected, dict) or selected.get("state") != "SUCCEEDED":
        raise ReadRejected("Mac Browser Plane 获取网页失败")
    result = selected.get("result")
    if not isinstance(result, dict):
        raise ReadRejected("Mac Browser Plane 结果缺失")
    status = result.get("status")
    if isinstance(status, int) and not 200 <= status < 300:
        raise ReadRejected("网页没有返回成功状态")
    final_url = _public_https(result.get("url", url))
    job_id = selected.get("job_id")
    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", job_id):
        raise ReadRejected("Browser Plane 任务标识无效")
    body = _read_artifact(result, job_id)
    if not body.strip():
        raise ReadRejected("该网页没有可读正文")
    return {
        "ok": True, "url": final_url,
        "text": body, "engine": str(result.get("engine") or selected.get("selected_capability") or "C0"),
        "job_id": job_id,
    }


def _process(request_path: Path, responses: Path, command: Path) -> None:
    request_id = request_path.stem
    if not ID.fullmatch(request_id) or request_path.is_symlink():
        request_path.unlink(missing_ok=True)
        return
    response_path = responses / (request_id + ".json")
    if response_path.exists():
        request_path.unlink(missing_ok=True)
        return
    answer: dict = {"id": request_id, "ok": False, "error": "Mac Browser Plane 网页读取失败"}
    try:
        if request_path.stat().st_size > 8192:
            raise ReadRejected("请求体积超限")
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        now = time.time()
        if (not isinstance(payload, dict) or payload.get("version") != 1
                or payload.get("id") != request_id
                or not isinstance(payload.get("created_at"), (int, float))
                or not isinstance(payload.get("expires_at"), (int, float))
                or payload["created_at"] > now + 10
                or payload["expires_at"] < now
                or payload["expires_at"] > now + 111):
            raise ReadRejected("请求过期或格式无效")
        url = _public_https(payload.get("url"))
        answer.update(_acquire(url, command))
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        # Do not forward raw subprocess errors, URLs or filesystem paths.
        answer["error"] = (
            str(exc) if isinstance(exc, ReadRejected) else "Mac Browser Plane 获取网页失败"
        )[:180]
    try:
        _atomic_response(response_path, answer)
    finally:
        request_path.unlink(missing_ok=True)


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    root = Path(sys.argv[1]).expanduser()
    command = Path(sys.argv[2]).expanduser()
    if (root.is_symlink() or not root.is_dir() or
            any(not (root / sub).is_dir() or (root / sub).is_symlink()
                for sub in ("requests", "responses")) or
            not command.is_file()):
        return 2
    lock = root / "host-worker.lock"
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        requests, responses = root / "requests", root / "responses"
        # An interrupted atomic request write must not keep launchd awake forever.
        for temp in requests.glob("*.tmp"):
            if not temp.is_symlink() and temp.is_file() and time.time() - temp.stat().st_mtime > 120:
                temp.unlink(missing_ok=True)
        # Responses of callers that timed out cannot persist indefinitely.
        for stale in responses.glob("*.json"):
            if not stale.is_symlink() and stale.is_file() and time.time() - stale.stat().st_mtime > 86400:
                stale.unlink(missing_ok=True)
        for item in sorted(requests.glob("*.json"))[:20]:
            _process(item, responses, command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
