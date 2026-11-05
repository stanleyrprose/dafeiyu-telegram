"""Targeted SQLite persistence regression using AstrBot's actual ORM API.

One unique throwaway preference is committed, reread in a separate ORM
engine, then deleted in finally. Does not touch user conversation rows.
"""
from __future__ import annotations
import asyncio
import secrets
from sqlmodel import col, delete
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.db.po import Preference

PATH = "/AstrBot/data/data_v4.db"

async def make_db():
    db = SQLiteDatabase(PATH)
    db.inited = True  # Existing schema; avoid startup PRAGMA/DDL.
    return db

async def main() -> None:
    scope_id = "test-" + secrets.token_hex(12)
    first = await make_db()
    second = None
    try:
        await first.insert_preference_or_update(
            "dafeiyu-sqlite-acceptance", scope_id, "roundtrip", {"val": "ok"},
        )
        await first.engine.dispose()
        second = await make_db()
        result = await second.get_preference(
            "dafeiyu-sqlite-acceptance", scope_id, "roundtrip",
        )
        print("orm_persistent_read:", bool(result and result.value == {"val": "ok"}))
    finally:
        # Clean up the exact unique row only.
        cleaner = await make_db()
        try:
            async with cleaner.get_db() as session:
                async with session.begin():
                    await session.execute(
                        delete(Preference).where(
                            Preference.scope == "dafeiyu-sqlite-acceptance",
                            Preference.scope_id == scope_id,
                            Preference.key == "roundtrip",
                        )
                    )
        finally:
            await cleaner.engine.dispose()
        if second is not None:
            await second.engine.dispose()
        await first.engine.dispose()
    check = await make_db()
    try:
        absent = await check.get_preference(
            "dafeiyu-sqlite-acceptance", scope_id, "roundtrip",
        )
        print("probe_cleanup_confirmed:", absent is None)
    finally:
        await check.engine.dispose()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("sqlite_regression_error_type:", type(exc).__name__)
        raise SystemExit(1)
