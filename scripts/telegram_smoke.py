#!/usr/bin/env python3
"""Telegram API smoke: local secrets only; print no Bot token or private URL."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def _load() -> tuple[str, str]:
    private = ROOT / "private"
    text = (private / "telegram" / "bot_token").read_text(encoding="utf-8").strip()
    env = (private / "deploy.env").read_text(encoding="utf-8").splitlines()
    owner = [line.partition("=")[2] for line in env if line.startswith("DAFEIYU_OWNER_USER_ID=")]
    if len(owner) != 1 or not owner[0].isdigit() or ":" not in text:
        raise ValueError("Bot Token 或 Owner 配置无效")
    return text, owner[0]


def _call(token: str, method: str, data: dict | None = None) -> dict:
    url = "https://api.telegram.org/bot" + token + "/" + method
    encoded = urlencode(data or {}).encode()
    try:
        with urlopen(Request(url, data=encoded, method="POST"), timeout=20) as reply:
            body = json.loads(reply.read())
    except HTTPError as exc:
        raise RuntimeError(f"Telegram API HTTP {exc.code}；正文与 URL 已隐藏") from None
    except URLError as exc:
        raise RuntimeError(f"Telegram 网络失败：{type(exc.reason).__name__}，已隐藏 URL") from None
    if not isinstance(body, dict) or not body.get("ok"):
        code = body.get("error_code", "unknown") if isinstance(body, dict) else "unknown"
        raise RuntimeError(f"Telegram API 拒绝：{code}；正文已隐藏")
    return body.get("result") or {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="给 Owner 主动发送单条测试消息")
    opts = parser.parse_args()
    token, owner = _load()
    me = _call(token, "getMe")
    print("getMe:", "OK" if me.get("is_bot") else "INVALID")
    webhook = _call(token, "getWebhookInfo")
    print("has_webhook:", bool(webhook.get("url")))
    if webhook.get("url"):
        print("现有 Webhook 已配置，不能与长轮询并行；未更改远端设置。")
        return 2
    if opts.send:
        marker = uuid.uuid4().hex[:8]
        response = _call(
            token,
            "sendMessage",
            {
                "chat_id": owner,
                "text": "🐋 大肥鱼 Mac mini 实际投递验收 " + marker
                + "\n如果你看到此消息，请直接回复机器人：你好，肥鱼。"
                + "\n（此为单次测试消息）",
            },
        )
        print("sendMessage:", "OK" if response.get("message_id") else "NO_MESSAGE_ID")
        print("marker:", marker)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else f"本地配置错误：{type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
