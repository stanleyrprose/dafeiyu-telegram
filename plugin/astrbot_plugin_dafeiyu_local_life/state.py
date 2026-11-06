"""Small durable state store for one-owner reminders, todos, and rhythm.

Separate from AstrBot's core database. Every write is a short SQLite transaction.
Delivery is at-most-once automatic: crash/timeout after claim requires manual retry.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LifeStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def initialize(self) -> None:
        if self.path.is_symlink():
            raise ValueError("Refusing symlink database")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (kind IN ('todo','reminder')),
                    text TEXT NOT NULL,
                    due_utc TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS task_due ON tasks(kind,status,due_utc);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity (
                    day TEXT PRIMARY KEY,
                    messages INTEGER NOT NULL,
                    last_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nudge_log (
                    day TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    at_utc TEXT NOT NULL
                );
            """)
        os.chmod(self.path, 0o600)

    def add_task(self, kind: str, description: str, due_utc: str | None = None) -> int:
        if kind not in ("todo", "reminder"):
            raise ValueError("Invalid task kind")
        text = description.strip()
        if not text or len(text) > 300:
            raise ValueError("Task must contain 1-300 characters")
        if kind == "reminder" and not due_utc:
            raise ValueError("Reminder needs a due timestamp")
        now = utc_now()
        with closing(self._connect()) as db, db:
            result = db.execute(
                "INSERT INTO tasks(kind,text,due_utc,status,created_utc,updated_utc)"
                " VALUES(?,?,?,'pending',?,?)",
                (kind, text, due_utc, now, now),
            )
            return result.lastrowid

    def list_tasks(self, kind: str | None = None, active_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        params: list[str] = []
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if active_only:
            sql += " AND status IN ('pending','claimed','unknown','failed')"
        sql += " ORDER BY COALESCE(due_utc, created_utc), id LIMIT 60"
        with closing(self._connect()) as db:
            return [dict(x) for x in db.execute(sql, params)]

    def change_task(self, task_id: int, status: str, allowed: tuple[str, ...]) -> bool:
        if status not in {"done", "cancelled", "pending"}:
            raise ValueError("Invalid status")
        with closing(self._connect()) as db, db:
            query = ("UPDATE tasks SET status=?,updated_utc=? WHERE id=? AND status IN ("
                     + ",".join("?" for _ in allowed) + ")")
            result = db.execute(query, (status, utc_now(), task_id, *allowed))
            return result.rowcount == 1

    def claim_due(self, at_utc: str, limit: int = 8) -> list[dict]:
        # One durable claim per task before contacting Telegram. No silent resend.
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = [dict(x) for x in db.execute(
                    "SELECT * FROM tasks WHERE kind='reminder' AND status='pending'"
                    " AND due_utc<=? ORDER BY due_utc,id LIMIT ?",
                    (at_utc, limit),
                )]
                for row in rows:
                    db.execute(
                        "UPDATE tasks SET status='claimed',updated_utc=?"
                        " WHERE id=? AND status='pending'",
                        (at_utc, row["id"]),
                    )
                db.commit()
                return rows
            except Exception:
                db.rollback()
                raise

    def record_delivery(self, task_id: int, succeeded: bool) -> None:
        status = "sent" if succeeded else "unknown"
        with closing(self._connect()) as db, db:
            db.execute("UPDATE tasks SET status=?,updated_utc=?"
                       " WHERE id=? AND status='claimed'",
                       (status, utc_now(), task_id))

    def recover_unknown(self) -> None:
        with closing(self._connect()) as db, db:
            db.execute("UPDATE tasks SET status='unknown',updated_utc=?"
                       " WHERE status='claimed'", (utc_now(),))

    def setting(self, key: str, default: str = "") -> str:
        with closing(self._connect()) as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO settings(key,value) VALUES(?,?)"
                       " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, value))

    def note_interaction(self, now: datetime | None = None, tz_name: str = "UTC") -> None:
        now = now or datetime.now(timezone.utc)
        day = now.astimezone(ZoneInfo(tz_name)).date().isoformat()
        instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO activity(day,messages,last_utc) VALUES(?,1,?)"
                " ON CONFLICT(day) DO UPDATE SET messages=messages+1,last_utc=excluded.last_utc",
                (day, instant),
            )

    def activity_summary(self, today: str) -> dict:
        with closing(self._connect()) as db:
            last = db.execute("SELECT last_utc FROM activity ORDER BY day DESC LIMIT 1").fetchone()
            week = db.execute(
                "SELECT COUNT(*) active_days,SUM(messages) messages"
                " FROM activity WHERE day>=date(?,'-6 days') AND day<=?",
                (today, today),
            ).fetchone()
        return {
            "last_utc": last["last_utc"] if last else None,
            "active_days": week["active_days"] or 0,
            "messages": week["messages"] or 0,
        }

    def claim_nudge(self, day: str) -> bool:
        with closing(self._connect()) as db, db:
            return db.execute(
                "INSERT OR IGNORE INTO nudge_log(day,status,at_utc)"
                " VALUES(?,'unknown',?)",
                (day, utc_now()),
            ).rowcount == 1

    def finish_nudge(self, day: str, succeeded: bool) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE nudge_log SET status=?,at_utc=? WHERE day=?",
                ("sent" if succeeded else "unknown", utc_now(), day),
            )
