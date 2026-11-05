"""Targeted v1.3 regressions; AstrBot-dependent paths require the pinned runtime."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import importlib.util

# CI runs pure-Python tests; the plugin integration suite runs in AstrBot Docker.
HAS_ASTRBOT = importlib.util.find_spec("astrbot") is not None
if HAS_ASTRBOT:
    from telegram.constants import ChatType
    from astrbot.core.exceptions import EmptyModelOutputError
    from data.plugins.astrbot_plugin_dafeiyu_siwc.main import OwnerTelegramAdapter
    from data.plugins.astrbot_plugin_dafeiyu_siwc.provider import (
        DafeiyuSIWCProvider, SIWCError, _expires_soon, _history,
    )
    from data.plugins.astrbot_plugin_dafeiyu_local_life.main import LocalLife


@unittest.skipUnless(HAS_ASTRBOT, "Requires pinned AstrBot Docker runtime")
class V13PureCases(unittest.TestCase):
    def test_expiry_uses_advance_window(self):
        now = datetime.now(timezone.utc)
        healthy = {"saved_at": now.isoformat(), "expires_in": 3600}
        almost = {"saved_at": (now - timedelta(minutes=58)).isoformat(), "expires_in": 3600}
        self.assertFalse(_expires_soon(healthy))
        self.assertTrue(_expires_soon(almost))

    def test_history_discards_tools_and_images(self):
        provider = SimpleNamespace(_ensure_message_to_dicts=lambda items: items)
        items = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "reply", "tool_calls": [{"id": "old"}]},
            {"role": "tool", "content": "private result"},
            {"role": "user", "content": [{"type": "image_url", "url": "example"}, {"type": "text", "text": "a note"}]},
        ]
        self.assertEqual(
            _history(provider, items),
            [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "reply"},
             {"role": "user", "content": "a note"}],
        )

    def test_owner_private_gate_uses_numeric_chat_id(self):
        gate = object.__new__(OwnerTelegramAdapter)
        gate.owner_id = 1001
        def update(user_id, chat_id, chat_type):
            return SimpleNamespace(
                effective_user=SimpleNamespace(id=user_id),
                effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
            )
        self.assertTrue(gate._allowed(update(1001, 1001, ChatType.PRIVATE)))
        self.assertFalse(gate._allowed(update(1002, 1002, ChatType.PRIVATE)))
        self.assertFalse(gate._allowed(update(1001, -100123, ChatType.SUPERGROUP)))

    def test_notes_are_local_and_scoped(self):
        local = object.__new__(LocalLife)
        local.umo = "telegram_owner:FriendMessage:1001"
        with tempfile.TemporaryDirectory() as folder:
            local.notes_file = Path(folder) / "notes.json"
            local._save_notes(["prefers concise answers"])
            self.assertEqual(local._load_notes(), ["prefers concise answers"])
        self.assertTrue(local._is_owner(SimpleNamespace(unified_msg_origin=local.umo)))
        self.assertFalse(local._is_owner(SimpleNamespace(unified_msg_origin="telegram_owner:FriendMessage:1002")))


@unittest.skipUnless(HAS_ASTRBOT, "Requires pinned AstrBot Docker runtime")
class V13ResponseCases(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_response_is_failure(self):
        provider = object.__new__(DafeiyuSIWCProvider)
        with self.assertRaises(SIWCError):
            await provider._parse_response(SimpleNamespace(status="incomplete"), None)

    async def test_completed_empty_final_uses_text_deltas(self):
        provider = object.__new__(DafeiyuSIWCProvider)
        provider._streamed_text_chunks = ["Hello", "!"]
        response = SimpleNamespace(
            status="completed", id="redacted", output=[],
            usage=SimpleNamespace(input_tokens=8, output_tokens=2,
                                  input_tokens_details=SimpleNamespace(cached_tokens=0)),
        )
        result = await provider._parse_response(response, None)
        self.assertFalse(result.is_chunk)
        self.assertEqual(result.completion_text, "Hello!")
        self.assertEqual(result.usage.output, 2)

    async def test_completed_without_delta_still_fails(self):
        provider = object.__new__(DafeiyuSIWCProvider)
        provider._streamed_text_chunks = []
        with self.assertRaises(EmptyModelOutputError):
            await provider._parse_response(SimpleNamespace(status="completed", output=[]), None)

    async def test_failed_response_never_reuses_delta(self):
        provider = object.__new__(DafeiyuSIWCProvider)
        provider._streamed_text_chunks = ["partial"]
        with self.assertRaises(SIWCError):
            await provider._parse_response(SimpleNamespace(status="failed", output=[]), None)


if __name__ == "__main__":
    unittest.main()
