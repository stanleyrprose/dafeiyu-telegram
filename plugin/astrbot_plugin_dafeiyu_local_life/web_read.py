"""Read-only public search and bounded HTTPS page extraction.

Never opens local network hosts, sends cookies, executes JS, or follows unchecked
redirects. DNS is resolved and the connection is pinned to a checked global IP.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin


class UnsafeURL(ValueError):
    pass


def _public_target(url: str) -> tuple[str, str, str]:
    if not isinstance(url, str) or len(url) > 2048:
        raise UnsafeURL("网页地址过长或无效")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeURL("只能读取公开 HTTPS 页面")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise UnsafeURL("不允许凭据或自定义端口")
    host = parsed.hostname.rstrip(".").lower()
    if not host or "." not in host or any(
        host.endswith(x) for x in (".local", ".internal", ".localhost", ".test", ".invalid")
    ):
        raise UnsafeURL("不允许内网或本机地址")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeURL("不允许直接使用 IP 地址")
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL("目标域名无法解析") from exc
    if not records or any(not ipaddress.ip_address(row[4][0]).is_global for row in records):
        raise UnsafeURL("目标地址不是公开互联网主机")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return host, records[0][4][0], path


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname: str, address: str):
        super().__init__(hostname, port=443, timeout=12, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_address, 443), timeout=self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.blocks: list[str] = []
        self.buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "form"}:
            self.ignored += 1
        if tag in {"p", "h1", "h2", "h3", "li", "article", "br", "title"}:
            self._flush()

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "form"}:
            self.ignored = max(0, self.ignored - 1)
        if tag in {"p", "h1", "h2", "h3", "li", "article", "title"}:
            self._flush()

    def handle_data(self, data):
        if self.ignored == 0 and len(self.blocks) < 250:
            self.buffer.append(data)

    def _flush(self):
        line = re.sub(r"\s+", " ", " ".join(self.buffer)).strip()
        if line and len(line) > 2:
            self.blocks.append(line)
        self.buffer.clear()

    def extract(self) -> str:
        self._flush()
        return "\n".join(self.blocks)[:9000]


def fetch_public_page(url: str, redirects: int = 2) -> tuple[str, str]:
    current = url
    for attempt in range(redirects + 1):
        host, address, path = _public_target(current)
        connection = _PinnedHTTPS(host, address)
        try:
            connection.request("GET", path, headers={
                "User-Agent": "DafeiyuReadOnly/1.0",
                "Accept": "text/html,text/plain",
                "Accept-Encoding": "identity",
                "Cookie": "",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location or attempt >= redirects:
                    raise UnsafeURL("网页跳转过多")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise UnsafeURL(f"页面返回 HTTP {response.status}")
            content_type = (response.getheader("Content-Type") or "").lower()
            if not any(x in content_type for x in ("text/html", "text/plain")):
                raise UnsafeURL("该 URL 不是普通文本网页")
            maximum = 256 * 1024
            raw = response.read(maximum + 1)
            if len(raw) > maximum:
                raise UnsafeURL("页面太大，请提供更短的文章")
            content = raw.decode("utf-8", errors="replace")
            if "text/plain" in content_type:
                return current, content[:9000]
            parser = _PageText()
            parser.feed(content)
            return current, parser.extract()
        finally:
            connection.close()
    raise UnsafeURL("网页跳转过多")


def public_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    text = query.strip()
    if not 2 <= len(text) <= 180:
        raise ValueError("搜索词需要 2–180 个字符")
    # lazy import; pinned dependency is declared by the AstrBot plugin.
    from ddgs import DDGS

    rows = DDGS(timeout=9, verify=True).text(
        text, safesearch="moderate", max_results=min(max(limit, 1), 6)
    )
    results: list[dict[str, str]] = []
    for row in rows or []:
        link = str(row.get("href") or "").strip()
        try:
            parsed = urlsplit(link)
            if (parsed.scheme != "https" or not parsed.hostname or
                    parsed.username is not None or parsed.password is not None or
                    parsed.port not in (None, 443)):
                continue
            host = parsed.hostname.lower().rstrip(".")
            if (host in {"localhost", "localhost.localdomain"} or
                host.endswith((".local", ".internal", ".localhost", ".test"))):
                continue
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                continue
        except ValueError:
            continue
        results.append({
            "title": re.sub(r"\s+", " ", str(row.get("title") or ""))[:130],
            "url": link[:800],
            "snippet": re.sub(r"\s+", " ", str(row.get("body") or ""))[:350],
        })
        if len(results) >= limit:
            break
    return results
