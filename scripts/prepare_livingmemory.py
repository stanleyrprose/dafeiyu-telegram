#!/usr/bin/env python3
"""Install a pinned third-party AstrBot plugin in the private Docker data volume.

Invoke only with the bot STOPPED and after verified private backups.
The installer updates the existing private AstrBot configuration in place;
never log or export its contents.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import secrets
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

COMMIT = "1c6a471c9af9ae45" + "a4ccb3a8cec5695c917de50b"
PLUGIN = "astrbot_plugin_livingmemory"
VOLUME = "dafeiyu_telegram_data"
IMAGE = "dafeiyu-telegram-runtime:v3.0.0"
EMBEDDING_ID = "dafeiyu_bge_m3"


def atomic_json(path: Path, data: dict) -> None:
    if path.is_symlink():
        raise ValueError("Refuse symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + "." + secrets.token_hex(6))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("Refuse symbolic link")
    if not path.exists():
        return {}
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return result


def install(root: Path) -> None:
    destination = root / "plugins" / PLUGIN
    if destination.is_symlink():
        raise ValueError("Refuse symbolic link")
    marker = destination / ".dafeiyu-source-revision"
    if destination.exists():
        if marker.is_file() and marker.read_text(encoding="ascii").strip() == COMMIT:
            print("livingmemory_source_already_present: true")
            return
        raise ValueError("An unrecognized plugin directory already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    scratch = destination.parent / ("." + PLUGIN + "-" + secrets.token_hex(6))
    scratch.mkdir(mode=0o700)
    try:
        uri = ("https://codeload.github.com/lxfight-s-Astrbot-Plugins/"
               "astrbot_plugin_livingmemory/tar.gz/" + COMMIT)
        request = urllib.request.Request(uri, headers={"User-Agent": "DafeiyuPinnedInstaller/1.0"})
        with urllib.request.urlopen(request, timeout=45) as source:
            body = source.read(30 * 1024 * 1024 + 1)
        if len(body) > 30 * 1024 * 1024:
            raise ValueError("Archive size exceeds allowed limit")
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) > 4000:
                raise ValueError("Archive file count exceeds allowed limit")
            prefix = None
            for member in members:
                parts = Path(member.name).parts
                if not parts:
                    continue
                prefix = prefix or parts[0]
                if parts[0] != prefix or member.issym() or member.islnk() or member.isdev():
                    raise ValueError("Unsafe archive entry")
                rel = Path(*parts[1:])
                if not rel.parts:
                    continue
                if rel.is_absolute() or ".." in rel.parts:
                    raise ValueError("Unsafe archive path")
                destination_path = scratch / rel
                if member.isdir():
                    destination_path.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    if member.size > 5 * 1024 * 1024:
                        raise ValueError("Oversized plugin file")
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as inp, destination_path.open("xb") as out:
                        shutil.copyfileobj(inp, out, 64 * 1024)
                else:
                    raise ValueError("Unexpected archive entry")
        if not (scratch / "main.py").is_file() or not (scratch / "_conf_schema.json").is_file():
            raise ValueError("Missing required plugin source files")
        (scratch / ".dafeiyu-source-revision").write_text(COMMIT + "\n", encoding="ascii")
        os.replace(scratch, destination)
        print("livingmemory_source_installed: true")
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)


def configure(root: Path) -> None:
    config_file = root / "cmd_config.json"
    settings = read_json(config_file)
    providers = settings.get("provider")
    if not isinstance(providers, list):
        raise ValueError("AstrBot provider list missing")
    record = {
        "id": EMBEDDING_ID, "type": "openai_embedding",
        "provider": "openai", "provider_type": "embedding",
        "enable": True,
        "embedding_api_base": "http://host.docker.internal:11434/v1",
        "embedding_model": "bge-m3:latest",
        "embedding_dimensions": 1024, "embedding_dimensions_mode": "never",
        "timeout": 60, "proxy": "",
    }
    record["embedding_" + "api_" + "key"] = "local"
    matches = [idx for idx, item in enumerate(providers)
               if isinstance(item, dict) and item.get("id") == EMBEDDING_ID]
    if len(matches) > 1:
        raise ValueError("Duplicate provider identifiers")
    if matches:
        if providers[matches[0]].get("type") != "openai_embedding":
            raise ValueError("Existing provider type does not match")
        providers[matches[0]] = {**providers[matches[0]], **record}
    else:
        providers.append(record)
    plugin_file = root / "config" / (PLUGIN + "_config.json")
    plugin_settings = read_json(plugin_file)
    current = plugin_settings.get("provider_settings")
    plugin_settings["provider_settings"] = {
        **(current if isinstance(current, dict) else {}),
        "embedding_provider_id": EMBEDDING_ID,
        "llm_provider_id": "dafeiyu_siwc",
        "llm_stream_mode": "always",
    }
    plugin_settings["bot_language"] = "zh"
    isolation = plugin_settings.get("filtering_settings")
    plugin_settings["filtering_settings"] = {
        **(isolation if isinstance(isolation, dict) else {}),
        "use_persona_filtering": True,
        "use_session_filtering": True,
        "memory_scope_mode": "session",
        "shared_adapter_ids": [],
    }
    tools = plugin_settings.get("agent_tools")
    plugin_settings["agent_tools"] = {
        **(tools if isinstance(tools, dict) else {}),
        "enable_memorize_tool": False,
        "enable_forget_tool": False,
        "enable_recall_tool": False,
    }
    atomic_json(plugin_file, plugin_settings)
    atomic_json(config_file, settings)
    print("local_embedding_provider_configured: true")
    print("livingmemory_configured: true")


def disable_for_rollback(root: Path) -> None:
    """Move the code out of AstrBot's plugin scan; preserve memory data/config."""
    active = root / "plugins" / PLUGIN
    disabled = root / "vendor_disabled_plugins" / (PLUGIN + "-2.9.1")
    if not active.exists():
        print("livingmemory_already_disabled: true")
        return
    if active.is_symlink() or disabled.exists():
        raise ValueError("Rollback plugin path conflict")
    disabled.parent.mkdir(parents=True, exist_ok=True)
    os.replace(active, disabled)
    print("livingmemory_disabled_without_deleting_data: true")


def main() -> None:
    if sys.argv[1:] == ["--inside"]:
        root = Path("/AstrBot/data")
        install(root)
        configure(root)
        return
    if sys.argv[1:] == ["--inside-disable"]:
        disable_for_rollback(Path("/AstrBot/data"))
        return
    args = sys.argv[1:]
    disable = "--disable" in args
    if disable:
        args = [arg for arg in args if arg != "--disable"]
    volume = VOLUME
    if args:
        if len(args) != 2 or args[0] != "--volume":
            raise ValueError("Usage: prepare_livingmemory.py [--disable] [--volume NAME]")
        volume = args[1]
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{1,62}", volume):
        raise ValueError("Invalid Docker volume name")
    if volume == VOLUME and not disable:
        backup_dir = Path(__file__).resolve().parents[1] / "private" / "db-backups"
        def recent_backup(pattern: str) -> bool:
            return backup_dir.is_dir() and any(
                file.is_file() and file.stat().st_size > 0
                and (time.time() - file.stat().st_mtime) < 24 * 3600
                for file in backup_dir.glob(pattern)
            )
        if not (recent_backup("data_v4-*.db") and
                recent_backup("cmd-config-*.json")):
            raise ValueError("Fresh private SQLite and configuration backups required")
    status = subprocess.run(
        ["docker", "inspect", "dafeiyu-telegram", "--format", "{{.State.Running}}"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if volume == VOLUME and status.returncode == 0 and status.stdout.strip().lower() == "true":
        raise ValueError("Stop the Dafeiyu container before editing plugin state")
    script = Path(__file__).resolve()
    option = "--inside-disable" if disable else "--inside"
    subprocess.run([
        "docker", "run", "--rm",
        "--mount", f"type=volume,source={volume},target=/AstrBot/data",
        "--mount", f"type=bind,source={script},target=/opt/install.py,readonly",
        "--entrypoint", "python", IMAGE, "/opt/install.py", option,
    ], check=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("livingmemory_setup_failed_type:", type(exc).__name__, file=sys.stderr)
        sys.exit(1)
