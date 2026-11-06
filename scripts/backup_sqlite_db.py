#!/usr/bin/env python3
"""Consistent SQLite backup from the live Docker volume, without exporting secrets.

Use from Mac project root: python3 scripts/backup_sqlite_db.py
Backups are stored under private/db-backups/ with owner-only permissions.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / "private" / "db-backups"
VOLUME = "dafeiyu_telegram_data"
IMAGE = "soulter/astrbot:v4.29.4"


def write_backup() -> None:
    source = Path("/data/data_v4.db")
    if not source.is_file():
        raise FileNotFoundError("SQLite source missing in Docker volume")
    target = Path("/backups") / (
        "data_v4-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".db"
    )
    if target.exists():
        raise FileExistsError("Backup destination already exists")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30) as src:
            with sqlite3.connect(target, timeout=30) as dst:
                src.backup(dst, pages=128, sleep=0.1)
                check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError("Backup integrity check failed")
        os.chmod(target, 0o600)
        print("backup_integrity:", check)
        print("backup_size_bytes:", target.stat().st_size)
        print("backup_filename:", target.name)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def backup_life_state(
    folder: Path = Path("/data/plugin_data/dafeiyu_local_life"),
    backups: Path = Path("/backups"),
) -> None:
    """Preserve P1/P2 state and old notes alongside the core snapshot."""
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    database = folder / "state.sqlite3"
    if database.is_file() and not database.is_symlink():
        destination = backups / ("life-state-" + label + ".sqlite3")
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30) as src:
                with sqlite3.connect(destination, timeout=30) as dst:
                    src.backup(dst)
                    check = dst.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise RuntimeError("Local life state backup failed validation")
            os.chmod(destination, 0o600)
            print("local_life_state_backup:", "ok")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    notes = folder / "notes.json"
    if notes.is_file() and not notes.is_symlink():
        destination = backups / ("life-notes-" + label + ".json")
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as writer, notes.open("rb") as reader:
                shutil.copyfileobj(reader, writer, length=8192)
                writer.flush()
                os.fsync(writer.fileno())
            os.chmod(destination, 0o600)
            print("local_life_notes_backup:", "ok")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise


def main() -> None:
    if sys.argv[1:] == ["--inside-volume"]:
        write_backup()
        backup_life_state()
        return
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python3 scripts/backup_sqlite_db.py")
    BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(BACKUPS, 0o700)
    subprocess.run(
        [
            "docker", "run", "--rm",
            "--mount", f"type=volume,source={VOLUME},target=/data,readonly",
            "--mount", f"type=bind,source={BACKUPS},target=/backups",
            "--mount", f"type=bind,source={Path(__file__).resolve()},target=/opt/backup.py,readonly",
            "--entrypoint", "python", IMAGE, "/opt/backup.py", "--inside-volume",
        ],
        check=True,
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, sqlite3.Error, subprocess.CalledProcessError, RuntimeError) as exc:
        print("backup_failed_type:", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
