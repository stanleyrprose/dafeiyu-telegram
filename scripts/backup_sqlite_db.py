"""Make a consistent SQLite online backup before any recovery action."""
from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/astrbot/data/data_v4.db"
BACKUPS = ROOT / "private" / "db-backups"


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError("Runtime SQLite DB missing")
    BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(BACKUPS, 0o700)
    target = BACKUPS / ("data_v4-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".db")
    if target.exists():
        raise FileExistsError("Backup destination already exists")
    with sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True, timeout=20) as src:
        with sqlite3.connect(target, timeout=20) as dst:
            src.backup(dst, pages=128, sleep=0.1)
            outcome = dst.execute("PRAGMA integrity_check").fetchone()[0]
    os.chmod(target, 0o600)
    if outcome != "ok":
        raise RuntimeError("Backup failed integrity check")
    print("backup_integrity:", outcome)
    print("backup_mode:", oct(target.stat().st_mode & 0o777))
    print("backup_size_bytes:", target.stat().st_size)
    print("backup_file:", str(target.relative_to(ROOT)))


if __name__ == "__main__":
    main()
