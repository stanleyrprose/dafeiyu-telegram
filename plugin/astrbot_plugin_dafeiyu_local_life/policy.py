"""Deterministic reminder parsing and evidence-only nudge policy."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _aware_local(when: datetime, tz: ZoneInfo) -> datetime:
    aware = when.replace(tzinfo=tz)
    # Fail closed for impossible local wall times (DST gaps).
    restored = aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    if restored != when:
        raise ValueError("本地时间不存在，请指定其他时间")
    return aware


def parse_reminder(expression: str, tz_name: str, now: datetime | None = None) -> tuple[str, str]:
    """Return (UTC ISO due, description) for *explicitly timed* commands."""
    zone = ZoneInfo(tz_name)
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    value = expression.strip()
    minutes = re.fullmatch(r"(?:(\d{1,4})\s*分钟|(\d{1,3})\s*小时)后(?:提醒我)?\s*(.+)", value)
    if minutes:
        delay = int(minutes[1] or minutes[2]) * (1 if minutes[1] else 60)
        due = local + timedelta(minutes=delay)
        text = minutes[3].strip()
    else:
        explicit = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})\s+(.+)", value)
        relative = re.fullmatch(
            r"(今天|明天|后天)\s*(上午|下午|晚上|中午|早上)?\s*(\d{1,2})(?::(\d{2})|点(半)?)"
            r"\s*(?:提醒我)?\s*(.+)", value
        )
        if explicit:
            try:
                day = datetime.strptime(explicit[1], "%Y-%m-%d").date()
                hour, minute, text = int(explicit[2]), int(explicit[3]), explicit[4].strip()
                due = _aware_local(datetime(day.year, day.month, day.day, hour, minute), zone)
            except (ValueError, OverflowError) as exc:
                raise ValueError("日期或时间无效") from exc
        elif relative:
            day = (local + timedelta(days={"今天": 0, "明天": 1, "后天": 2}[relative[1]])).date()
            hour = int(relative[3])
            minute = 30 if relative[5] else int(relative[4] or 0)
            part = relative[2] or ""
            if part in ("下午", "晚上") and hour < 12:
                hour += 12
            if part in ("上午", "早上") and hour == 12:
                hour = 0
            if part == "中午" and hour < 11:
                hour += 12
            text = relative[6].strip()
            try:
                due = _aware_local(datetime(day.year, day.month, day.day, hour, minute), zone)
            except ValueError as exc:
                raise ValueError("日期或时间无效") from exc
        else:
            raise ValueError("请指定准确时间，例如 /remind 明天上午9点提醒我开会")
    if not text or len(text) > 300:
        raise ValueError("提醒事项长度必须为 1–300 字")
    delta = (due.astimezone(timezone.utc) - local.astimezone(timezone.utc)).total_seconds()
    if delta < 30 or delta > 366 * 86400:
        raise ValueError("提醒时间需要晚于当前至少30秒，且不超过366天")
    return due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), text


def format_due(due_utc: str, tz_name: str) -> str:
    moment = datetime.strptime(due_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return moment.astimezone(ZoneInfo(tz_name)).strftime("%m-%d %H:%M")


PRIVATE_TERMS = re.compile(
    r"密码|口令|密钥|验证码|token|secret|api.key|身份证|护照|住址|具体地址|"
    r"银行账号|卡号|病史|诊断|处方|药物|怀孕|工资|客户合同|合同金额|商业机密|"
    r"病情|医疗记录|政治倾向|宗教|性取向|私钥|助记词|手机号|邮箱|"
    r"客户|报价|招投标|投标|财务数据|账号|银行卡|公司内部|机密|商业计划",
    re.IGNORECASE,
)
IDENTIFIER = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{8,}\b", re.IGNORECASE)


def safe_memory(memory: str, evidence: str, source: str, category: str, score: float) -> bool:
    """No personal/sensitive facts; stable preferences/goals need literal quote evidence."""
    if category not in {"preference", "goal"} or not math.isfinite(score) or not 0.87 <= score <= 1:
        return False
    if not 5 <= len(memory) <= 150 or not 4 <= len(evidence) <= 150:
        return False
    if evidence not in source or PRIVATE_TERMS.search(source) or IDENTIFIER.search(source):
        return False
    if PRIVATE_TERMS.search(memory) or PRIVATE_TERMS.search(evidence):
        return False
    if IDENTIFIER.search(memory) or IDENTIFIER.search(evidence):
        return False
    return True


def daily_nudge(
    tasks: list[dict], activity: dict, now: datetime, tz_name: str
) -> str | None:
    """Only grounded counts; never fabricate activity or promise completed operations."""
    local = now.astimezone(ZoneInfo(tz_name))
    latest = activity.get("last_utc")
    if latest:
        try:
            previous = datetime.strptime(latest, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if (now - previous).total_seconds() < 6 * 3600:
                return None
        except ValueError:
            pass
    open_todos = [t for t in tasks if t["kind"] == "todo" and t["status"] == "pending"]
    waiting = [t for t in tasks if t["kind"] == "reminder" and t["status"] == "pending"]
    due_soon = [t for t in waiting if t["due_utc"][:10] <=
                (now + timedelta(days=1)).astimezone(timezone.utc).strftime("%Y-%m-%d")]
    uncertain = [t for t in tasks if t["status"] in ("unknown", "failed")]
    if not (open_todos or due_soon or uncertain):
        return None
    parts = ["🐋 肥鱼今天的小提醒（来自本地待办记录）："]
    if open_todos:
        parts.append(f"还有 {len(open_todos)} 项待办；最早的一项是「{open_todos[0]['text'][:70]}」。")
    if due_soon:
        parts.append(f"未来约一天内有 {len(due_soon)} 项提醒。")
    if uncertain:
        parts.append(f"有 {len(uncertain)} 条提醒状态待确认，发送 /reminders 查看。")
    parts.append("今天挑一项处理就好；不必把所有事情一次做完。")
    return "\n".join(parts)
