"""Explicit owner calendar expressions, timezone-safe; no inferred dates."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def event_interval(expression: str, zone_name: str,
                   now: datetime | None = None) -> tuple[str, str, str]:
    # Deliberately require full start time and duration; do not infer a workday.
    found = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})\s+(\d{1,3})\s+(.+)",
        expression.strip(),
    )
    if not found:
        raise ValueError("用法：/event 2026-11-10 09:00 60 项目会议（时间+分钟数+事项）")
    title = found[5].strip()
    length = int(found[4])
    if not 1 <= len(title) <= 180 or not 5 <= length <= 480:
        raise ValueError("事项为1-180字；日程时长为5-480分钟")
    try:
        day = datetime.strptime(found[1], "%Y-%m-%d")
        wall = day.replace(hour=int(found[2]), minute=int(found[3]))
        zone = ZoneInfo(zone_name)
        local = wall.replace(tzinfo=zone)
        if local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != wall:
            raise ValueError("该本地时间不存在")
    except (ValueError, OverflowError) as exc:
        raise ValueError("日期或时间无效") from exc
    start = local.astimezone(timezone.utc)
    present = now or datetime.now(timezone.utc)
    offset = (start - present).total_seconds()
    if offset <= 30 or offset > 366 * 86400:
        raise ValueError("仅支持30秒之后、366天以内的日程")
    finish = start + timedelta(minutes=length)
    return (start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            finish.strftime("%Y-%m-%dT%H:%M:%SZ"),
            title)


def display_utc(iso: str, zone_name: str) -> str:
    parsed = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo(zone_name)).strftime("%Y-%m-%d %H:%M")


def is_quiet_time(now: datetime, zone_name: str, start: int = 23, end: int = 8) -> bool:
    hour = now.astimezone(ZoneInfo(zone_name)).hour
    return (start <= hour or hour < end) if start > end else (start <= hour < end)


def scheduled_contact_slot(now: datetime, zone_name: str, key: str) -> bool:
    """Only two 30-minute slots per day, computed deterministically per kind."""
    from hashlib import sha256
    local = now.astimezone(ZoneInfo(zone_name))
    day = local.date().isoformat()
    slot = int.from_bytes(sha256((day + ":" + key).encode()).digest()[:2], "big") % 18
    # 09:00..17:30, 18 half-hour slots. A second check won't send twice.
    target = 9 * 2 + slot
    return (local.hour * 2 + (local.minute // 30)) == target
