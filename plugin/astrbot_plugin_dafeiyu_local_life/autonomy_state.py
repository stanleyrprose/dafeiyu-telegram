"""Owner-scoped autonomy state built atop the existing local LifeStore SQLite.

Adds calendar, public discovery dedup and a shared proactive contact ledger.
All changes use the existing private Docker volume, not a new service.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from .state import LifeStore, utc_now


class AutonomyStore(LifeStore):
    def initialize(self) -> None:
        super().initialize()
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_utc TEXT NOT NULL,
                    end_utc TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled'
                        CHECK(status IN ('scheduled','cancelled','done')),
                    reminder_id INTEGER,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_calendar_due
                    ON calendar_events(status,start_utc);
                CREATE TABLE IF NOT EXISTS watch_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL CHECK(source IN ('x','reddit')),
                    query TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_checked_utc TEXT,
                    UNIQUE(source,query)
                );
                CREATE TABLE IF NOT EXISTS discovery_seen (
                    digest TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    first_seen_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outreach (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('claimed','sent','unknown')),
                    claimed_utc TEXT NOT NULL,
                    replied_utc TEXT
                );
            """)
        self.recover_outreach()


    def change_task(self, task_id: int, status: str, allowed: tuple[str, ...]) -> bool:
        linked_event_id = None
        with closing(self._connect()) as db:
            row = db.execute("SELECT kind FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or (status == "done" and row["kind"] != "todo"):
                return False
            if status == "cancelled":
                event = db.execute(
                    "SELECT id FROM calendar_events WHERE reminder_id=?"
                    " AND status='scheduled'", (task_id,),
                ).fetchone()
                linked_event_id = event["id"] if event else None
        if linked_event_id is not None:
            return self.cancel_event(linked_event_id)
        return super().change_task(task_id, status, allowed)

    def add_event(self, title: str, start_utc: str, end_utc: str) -> tuple[int, int]:
        text = title.strip()
        if not 1 <= len(text) <= 180:
            raise ValueError("日程标题长度必须为1-180字")
        if not start_utc < end_utc:
            raise ValueError("结束时间必须晚于开始时间")
        with closing(self._connect()) as db, db:
            conflicts = db.execute(
                "SELECT count(*) FROM calendar_events WHERE status='scheduled'"
                " AND start_utc<? AND end_utc>?",
                (end_utc, start_utc),
            ).fetchone()[0]
            now = utc_now()
            reminder_id = db.execute(
                "INSERT INTO tasks(kind,text,due_utc,status,created_utc,updated_utc)"
                " VALUES('reminder',?,?,'pending',?,?)",
                ('[日程] ' + text, start_utc, now, now),
            ).lastrowid
            result = db.execute(
                "INSERT INTO calendar_events(title,start_utc,end_utc,reminder_id,created_utc,updated_utc)"
                " VALUES(?,?,?,?,?,?)",
                (text, start_utc, end_utc, reminder_id, now, now),
            )
            return result.lastrowid, conflicts

    def list_events(self, start_utc: str, end_utc: str, limit: int = 25) -> list[dict]:
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM calendar_events WHERE status='scheduled'"
                " AND start_utc<? AND end_utc>? ORDER BY start_utc,id LIMIT ?",
                (end_utc, start_utc, limit),
            )]

    def get_event(self, number: int) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM calendar_events WHERE id=? AND status='scheduled'",
                (number,),
            ).fetchone()
            return dict(row) if row else None

    def update_event(self, number: int, start_utc: str, end_utc: str) -> bool:
        if not start_utc < end_utc:
            raise ValueError("日程结束时间必须晚于开始")
        with closing(self._connect()) as db, db:
            original = db.execute(
                "SELECT reminder_id FROM calendar_events WHERE id=? AND status='scheduled'",
                (number,),
            ).fetchone()
            if original is None:
                return False
            changed = db.execute(
                "UPDATE tasks SET due_utc=?,updated_utc=?"
                " WHERE id=? AND status='pending'",
                (start_utc, utc_now(), original['reminder_id']),
            )
            if changed.rowcount != 1:
                return False  # Cannot reschedule a reminder already claimed/sent.
            db.execute(
                "UPDATE calendar_events SET start_utc=?,end_utc=?,updated_utc=?"
                " WHERE id=? AND status='scheduled'",
                (start_utc, end_utc, utc_now(), number),
            )
            return True

    def cancel_event(self, number: int) -> bool:
        with closing(self._connect()) as db, db:
            item = db.execute(
                "SELECT reminder_id FROM calendar_events WHERE id=? AND status='scheduled'",
                (number,),
            ).fetchone()
            if item is None:
                return False
            db.execute(
                "UPDATE tasks SET status='cancelled',updated_utc=?"
                " WHERE id=? AND status='pending'", (utc_now(), item['reminder_id']),
            )
            db.execute(
                "UPDATE calendar_events SET status='cancelled',updated_utc=?"
                " WHERE id=? AND status='scheduled'", (utc_now(), number),
            )
            return True

    def add_topic(self, source: str, query: str) -> int:
        if source not in ("x", "reddit"):
            raise ValueError("平台只能是 x 或 reddit")
        value = " ".join(query.strip().split())
        if not 2 <= len(value) <= 100:
            raise ValueError("追踪主题必须为2-100字")
        with closing(self._connect()) as db, db:
            count = db.execute("SELECT count(*) FROM watch_topics WHERE enabled=1").fetchone()[0]
            exists = db.execute(
                "SELECT id,enabled FROM watch_topics WHERE source=? AND query=?",
                (source, value),
            ).fetchone()
            if exists:
                if not exists["enabled"] and count >= 12:
                    raise ValueError("最多同时追踪12个主题")
                db.execute("UPDATE watch_topics SET enabled=1 WHERE id=?", (exists["id"],))
                return exists["id"]
            if count >= 12:
                raise ValueError("最多同时追踪12个主题")
            return db.execute(
                "INSERT INTO watch_topics(source,query) VALUES(?,?)", (source, value),
            ).lastrowid

    def list_topics(self, enabled_only: bool = False) -> list[dict]:
        with closing(self._connect()) as db:
            sql = ("SELECT id,source,query,enabled,last_checked_utc"
                   " FROM watch_topics WHERE enabled=1 ORDER BY id"
                   if enabled_only else
                   "SELECT id,source,query,enabled,last_checked_utc FROM watch_topics ORDER BY id")
            return [dict(r) for r in db.execute(sql)]

    def pause_topic(self, number: int) -> bool:
        with closing(self._connect()) as db, db:
            return db.execute(
                "UPDATE watch_topics SET enabled=0 WHERE id=? AND enabled=1",
                (number,),
            ).rowcount == 1

    def mark_checked(self, number: int) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE watch_topics SET last_checked_utc=? WHERE id=?",
                (utc_now(), number),
            )

    def unseen(self, url: str) -> bool:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        with closing(self._connect()) as db:
            return db.execute(
                "SELECT 1 FROM discovery_seen WHERE digest=?", (digest,),
            ).fetchone() is None

    def remember_links(self, source: str, urls: list[str]) -> None:
        now = utc_now()
        limit = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM discovery_seen WHERE first_seen_utc<?", (limit,))
            db.executemany(
                "INSERT OR IGNORE INTO discovery_seen(digest,source,first_seen_utc)"
                " VALUES(?,?,?)",
                [(hashlib.sha256(url.encode("utf-8")).hexdigest(), source, now) for url in urls],
            )

    def recover_outreach(self) -> None:
        # Never blindly resend after an interrupted send.
        with closing(self._connect()) as db, db:
            db.execute("UPDATE outreach SET state='unknown' WHERE state='claimed'")

    def claim_outreach(self, day: str, kind: str, silent_seconds: int = 0) -> bool:
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                pending = db.execute(
                    "SELECT 1 FROM outreach WHERE state IN ('sent','unknown','claimed')"
                    " AND replied_utc IS NULL LIMIT 1"
                ).fetchone()
                recent = db.execute(
                    "SELECT last_utc FROM activity ORDER BY last_utc DESC LIMIT 1"
                ).fetchone()
                if pending:
                    db.rollback()
                    return False
                if recent and silent_seconds:
                    last = datetime.strptime(recent[0], "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc,
                    )
                    if (datetime.now(timezone.utc) - last).total_seconds() < silent_seconds:
                        db.rollback()
                        return False
                db.execute(
                    "INSERT OR IGNORE INTO outreach(day,kind,state,claimed_utc)"
                    " VALUES(?,?,'claimed',?)", (day, kind, utc_now()),
                )
                accepted = db.execute("SELECT changes()").fetchone()[0] == 1
                db.commit()
                return accepted
            except Exception:
                db.rollback()
                raise

    def finish_outreach(self, day: str, succeeded: bool) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE outreach SET state=? WHERE day=? AND state='claimed'",
                ("sent" if succeeded else "unknown", day),
            )

    def record_owner_reply(self) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE outreach SET replied_utc=? WHERE id=("
                " SELECT id FROM outreach WHERE state IN ('sent','unknown') AND replied_utc IS NULL"
                " ORDER BY id DESC LIMIT 1)",
                (utc_now(),),
            )

    def latest_outreach(self) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM outreach ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None
