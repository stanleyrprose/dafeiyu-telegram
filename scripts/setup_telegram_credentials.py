#!/usr/bin/env python3
"""One-time Mac SSH setup for a Telegram bot. The secret never enters chat/CLI args."""
from __future__ import annotations

import getpass
import os
import re
import secrets
import sys
import warnings
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PRIVATE = PROJECT / "private"
TOKEN_DIR = PRIVATE / "telegram"
TOKEN_FILE = TOKEN_DIR / "bot_token"
ENV_FILE = PRIVATE / "deploy.env"

# BotFather token shape only: no network validation here.
TOKEN_SHAPE = re.compile(r"[0-9]{5,16}:[A-Za-z0-9_-]{25,128}\Z")
OWNER_SHAPE = re.compile(r"[1-9][0-9]{0,19}\Z")


def ensure_private_directory(folder: Path) -> None:
    if folder.is_symlink():
        raise ValueError(f"拒绝使用符号链接目录：{folder}")
    folder.mkdir(mode=0o700, parents=False, exist_ok=True)
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError(f"无效的私有目录：{folder}")
    os.chmod(folder, 0o700)


def atomic_write(path: Path, content: str) -> None:
    if path.is_symlink():
        raise ValueError("拒绝覆盖符号链接")
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def update_owner_env(owner: str) -> str:
    if ENV_FILE.is_symlink():
        raise ValueError("拒绝读取符号链接环境文件")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    result = [line for line in lines if not line.strip().startswith("DAFEIYU_OWNER_USER_ID=")]
    result.append("DAFEIYU_OWNER_USER_ID=" + owner)
    return "\n".join(result) + "\n"


def main() -> int:
    if not sys.stdin.isatty():
        print("请在交互式 SSH 终端执行，不能从管道读取 Token。", file=sys.stderr)
        return 1

    print("大肥鱼 Telegram 本机凭据配置（Token 不回显、不上传、不写入 Git）")
    owner = input("输入你的 Telegram 数字 User ID（不是 Bot ID）：").strip()
    if not OWNER_SHAPE.fullmatch(owner):
        print("Owner ID 必须是正整数。", file=sys.stderr)
        return 1

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("粘贴 @BotFather 提供的 Bot Token（输入不显示）：").strip()
    except (EOFError, getpass.GetPassWarning):
        print("无法安全关闭终端回显，请使用交互式 SSH 终端。", file=sys.stderr)
        return 1
    if not TOKEN_SHAPE.fullmatch(token):
        print("Token 格式不像 BotFather Token。请检查是否粘贴完整。", file=sys.stderr)
        return 1

    if TOKEN_FILE.exists():
        confirm = input("已有 Token 文件。输入 REPLACE 才允许覆盖：").strip()
        if confirm != "REPLACE":
            print("已取消，原凭据未改动。")
            return 1

    ensure_private_directory(PRIVATE)
    ensure_private_directory(TOKEN_DIR)

    # Owner metadata is not a token. Keep other preexisting deployment settings.
    env_content = update_owner_env(owner)
    atomic_write(ENV_FILE, env_content)
    atomic_write(TOKEN_FILE, token + "\n")
    print("完成：Bot Token 已保存到本机私有文件（未显示内容）。")
    print("完成：Owner ID 已保存到本机私有部署配置。")
    print("可以返回 ChatGPT 告诉我“Telegram 凭据已配置”，不要发送 Token。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print("写入失败：" + str(exc), file=sys.stderr)
        raise SystemExit(1)
