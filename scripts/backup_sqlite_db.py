#!/usr/bin/env python3
"""Consistent SQLite and private configuration backup from the Docker volume.

Use from Mac project root: python3 scripts/backup_sqlite_db.py
Backups include sensitive AstrBot configuration; keep private/db-backups/ owner-only.
Never print, publish, or upload these files to Git.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
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


def backup_livingmemory_files(
    root: Path = Path("/data"),
    backups: Path = Path("/backups"),
) -> None:
    """Backup the third-party memory index/graph atomically when AstrBot is stopped."""
    folders = [
        root / "plugin_data" / "astrbot_plugin_livingmemory",
        root / "plugin_data" / "livingmemory",
        root / "plugins" / "astrbot_plugin_livingmemory",
    ]
    config = root / "config" / "astrbot_plugin_livingmemory_config.json"
    if not any(source.is_dir() for source in folders) and not config.is_file():
        return
    targets = []
    total = 0
    for source in folders:
        if source.is_symlink():
            raise ValueError("Refusing symlink to LivingMemory directory")
        if not source.is_dir():
            continue
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError("Refusing symlink in LivingMemory backup")
            if path.is_file():
                total += path.stat().st_size
                targets.append((path, str(source.relative_to(root)) + "/" +
                                str(path.relative_to(source))))
    if config.is_file():
        if config.is_symlink():
            raise ValueError("Refusing plugin config symlink")
        targets.append((config, "config/astrbot_plugin_livingmemory_config.json"))
    if len(targets) > 12000 or total > 1024 * 1024 * 1024:
        raise ValueError("LivingMemory data exceeds bounded backup size")
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backups / ("livingmemory-" + label + ".tar.gz")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                for path, relative in targets:
                    archive.add(path, arcname=relative, recursive=False)
        os.chmod(target, 0o600)
        print("livingmemory_snapshot:", "ok", "files:", len(targets))
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def backup_astrbot_config(
    root: Path = Path("/data"),
    backups: Path = Path("/backups"),
) -> None:
    """Private snapshot of original provider/token config needed for safe rollback."""
    source = root / "cmd_config.json"
    if not source.is_file() or source.is_symlink():
        raise ValueError("Private AstrBot config missing or unsafe")
    if source.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("AstrBot config is unexpectedly large")
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backups / ("cmd-config-" + label + ".json")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as writer, source.open("rb") as reader:
            shutil.copyfileobj(reader, writer, length=8192)
            writer.flush()
            os.fsync(writer.fileno())
        os.chmod(target, 0o600)
        print("private_config_backup:", "ok")
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def main() -> None:
    if sys.argv[1:] == ["--inside-volume"]:
        write_backup()
        backup_astrbot_config()
        backup_life_state()
        backup_livingmemory_files()
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
    except (OSError, sqlite3.Error, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print("backup_failed_type:", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
