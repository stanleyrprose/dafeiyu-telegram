#!/usr/bin/env python3
"""Provision a private AstrBot v4.29.4 config from owner-controlled local files.

Run on Mac after AstrBot generates its default cmd_config.json once.
The credential value stays on this Mac and is never printed or committed.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "runtime" / "astrbot" / "data"
CONFIG = DATA / "cmd_config.json"
SECRET_DIR = ROOT / "private"
BOT_FILE = SECRET_DIR / "telegram" / "bot_token"
DEPLOY_ENV = SECRET_DIR / "deploy.env"
OWNER_PATTERN = re.compile(r"[1-9][0-9]{0,19}\Z")
BOT_PATTERN = re.compile(r"[0-9]{5,16}:[A-Za-z0-9_-]{25,128}\Z")


def _private_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("缺少有效的本机私有文件")
    if path.stat().st_mode & 0o077:
        raise ValueError("私有文件权限过宽，拒绝使用")
    return path.read_text(encoding="utf-8").strip()


def _atomic_json(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError("拒绝覆盖符号链接")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        tmp.unlink(missing_ok=True)


def _owner_id(env_text: str) -> str:
    result = []
    for line in env_text.splitlines():
        if line.startswith("DAFEIYU_OWNER_USER_ID="):
            result.append(line.partition("=")[2].strip())
    if len(result) != 1 or not OWNER_PATTERN.fullmatch(result[0]):
        raise ValueError("Owner ID 配置无效")
    return result[0]


def main() -> int:
    raw_owner = _private_text(DEPLOY_ENV)
    owner = _owner_id(raw_owner)
    value = _private_text(BOT_FILE)
    if not BOT_PATTERN.fullmatch(value):
        raise ValueError("BotFather 凭据格式无效")
    if not CONFIG.is_file() or CONFIG.is_symlink():
        raise ValueError("AstrBot 尚未生成默认运行配置，请先完成无平台的首次启动")
    existing = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    if not isinstance(existing, dict):
        raise ValueError("AstrBot 运行配置无效")
    platform = dict(
        id="telegram_owner",
        type="telegram_owner",
        enable=True,
        telegram_token=value,
        start_message="你好，肥鱼在这儿。",
        telegram_api_base_url="https://api.telegram.org/bot",
        telegram_file_base_url="https://api.telegram.org/file/bot",
        telegram_command_register=False,
        telegram_command_auto_refresh=False,
        telegram_polling_restart_delay=5.0,
    )
    existing["platform"] = [platform]
    settings = existing.setdefault("platform_settings", {})
    settings.update({
        "enable_id_white_list": True,
        "id_whitelist": [f"telegram_owner:FriendMessage:{owner}"],
        "id_whitelist_log": False,
        "wl_ignore_admin_on_friend": False,
        "wl_ignore_admin_on_group": False,
        "no_permission_reply": False,
    })
    existing["provider"] = [{
        "id": "dafeiyu_siwc",
        "type": "dafeiyu_siwc",
        "provider_type": "chat_completion",
        "enable": True,
        "key": [],
        "model": "",
    }]
    runner = existing.setdefault("agent_runner", {})
    runner["runner_type"] = "local"
    runner.setdefault("config", {}).setdefault("model", {})["provider_id"] = "dafeiyu_siwc"
    provider = existing.setdefault("provider_settings", {})
    provider["streaming_response"] = True
    provider["web_search"] = False
    provider.setdefault("proactive_capability", {})["add_cron_tools"] = False
    existing["log_level"] = "INFO"
    existing["log_file_enable"] = False
    existing["trace_enable"] = False
    existing["platform_settings"]["segmented_reply"] = {"enable": False}
    existing["plugin_set"] = ["astrbot_plugin_dafeiyu_siwc", "astrbot_plugin_dafeiyu_local_life"]
    _atomic_json(CONFIG, existing)
    print("AstrBot 本地运行配置已更新（凭据内容已隐藏）。")
    print("Owner 白名单：已设为单一 Telegram 私聊；Provider：dafeiyu_siwc。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError) as exc:
        # Avoid dumping exception arguments from JSON, credential, or HTTP libraries.
        print(f"本地配置失败：{type(exc).__name__}。请检查私有文件和首次启动步骤。", file=sys.stderr)
        sys.exit(1)
