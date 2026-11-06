"""Bounded public-index discovery of X and Reddit posts.

Not a privileged X/Reddit API client: the indexed public search may be stale,
incomplete, or blocked. No account login, cookies, or scraping of Reddit pages.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .policy import PRIVATE_TERMS, IDENTIFIER
from .web_read import public_search


_X_POST = re.compile(r"^/[A-Za-z0-9_]{1,20}/status/(\d{6,24})(?:/)?$")
_R_POST = re.compile(r"^/r/[A-Za-z0-9_]{1,24}/comments/([A-Za-z0-9]{4,12})(?:/.*)?$")


def safe_topic(query: str) -> str:
    value = " ".join(query.split())
    if not 2 <= len(value) <= 100:
        raise ValueError("追踪词需要2-100字")
    if PRIVATE_TERMS.search(value) or IDENTIFIER.search(value):
        raise ValueError("不能将私人身份、健康、客户或凭据内容提交给公网搜索")
    return value


def canonical_public_post(source: str, url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return None
        host = (parsed.hostname or "").lower().strip(".")
        if parsed.port not in (None, 443):
            return None
        if source == "x" and host in ("x.com", "www.x.com", "twitter.com", "www.twitter.com"):
            match = _X_POST.fullmatch(parsed.path)
            return "https://x.com" + parsed.path.rstrip("/") if match else None
        if source == "reddit" and host in ("reddit.com", "www.reddit.com", "old.reddit.com"):
            match = _R_POST.fullmatch(parsed.path)
            if match:
                # Keep only a thread identifier, never any access tokens or tracking params.
                return f"https://www.reddit.com/r/{parsed.path.split('/')[2]}/comments/{match.group(1)}/"
    except ValueError:
        return None
    return None


def indexed_posts(source: str, topic: str, max_results: int = 6) -> list[dict]:
    if source not in ("x", "reddit"):
        raise ValueError("Unsupported source")
    query = safe_topic(topic)
    site = "x.com" if source == "x" else "reddit.com"
    # Search uses only a public discovery index; direct platform API access is not implied.
    rows = public_search(f"site:{site} {query}", min(6, max_results))
    results: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        url = canonical_public_post(source, row.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "source": source,
            "topic": query,
            "url": url,
            "title": re.sub(r"\s+", " ", str(row.get("title") or ""))[:120],
            "snippet": re.sub(r"\s+", " ", str(row.get("snippet") or ""))[:240],
        })
    return results


def format_discovery(items: list[dict]) -> str:
    if not items:
        return ""
    lines = ["🐋 肥鱼公开社区探索（搜索索引发现，非平台实时 API）"]
    for i, row in enumerate(items[:4], 1):
        label = "X" if row["source"] == "x" else "Reddit"
        lines.append(f"{i}. [{label} · {row['topic'][:40]}] {row['title'][:85]}\n{row['url']}")
    lines.append("这些是公开链接，不代表我已登录或阅读全文；可用 /explore off 暂停。")
    return "\n\n".join(lines)[:1600]
