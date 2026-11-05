"""Offline regression for the private Telegram configuration bootstrap."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "provision_telegram_runtime.py"
SPEC = importlib.util.spec_from_file_location("dafeiyu_provision", SCRIPT)
assert SPEC and SPEC.loader
PROVISION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVISION)


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        private = root / "private"
        private.mkdir(mode=0o700)
        telegram = private / "telegram"
        telegram.mkdir(mode=0o700)
        self.bot_file = telegram / "bot_token"
        self.bot_file.write_text("123456:" + "A" * 40 + "\n", encoding="utf-8")
        self.bot_file.chmod(0o600)
        self.env_file = private / "deploy.env"
        self.env_file.write_text("DAFEIYU_OWNER_USER_ID=24680\n", encoding="utf-8")
        self.env_file.chmod(0o600)
        data = root / "runtime" / "astrbot" / "data"
        data.mkdir(parents=True)
        self.config = data / "cmd_config.json"
        self.config.write_text(
            json.dumps({
                "platform": [],
                "provider": [],
                "agent_runner": {"runner_type": "local", "config": {"other": "keep"}},
                "platform_settings": {},
                "provider_settings": {},
                "log_level": "INFO",
            }),
            encoding="utf-8",
        )
        self.config.chmod(0o600)
        self.patches = [
            patch.object(PROVISION, "DEPLOY_ENV", self.env_file),
            patch.object(PROVISION, "BOT_FILE", self.bot_file),
            patch.object(PROVISION, "CONFIG", self.config),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def test_config_owner_gate_and_provider(self):
        self.assertEqual(PROVISION.main(), 0)
        data = json.loads(self.config.read_text())
        self.assertEqual(data["platform"][0]["id"], "telegram_owner")
        self.assertTrue(data["platform"][0]["telegram_token"].startswith("123456:"))
        self.assertEqual(data["provider"][0]["type"], "dafeiyu_siwc")
        self.assertEqual(data["platform_settings"]["id_whitelist"], ["telegram_owner:FriendMessage:24680"])
        self.assertEqual(data["agent_runner"]["config"]["other"], "keep")
        self.assertFalse(stat.S_IMODE(self.config.stat().st_mode) & 0o077)

    def test_rejects_exposed_private_file(self):
        self.bot_file.chmod(0o644)
        with self.assertRaises(ValueError):
            PROVISION.main()

    def test_rejects_missing_owner(self):
        self.env_file.write_text("DAFEIYU_OWNER_USER_ID=\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            PROVISION.main()

    def test_does_not_create_config_before_astrbot_first_boot(self):
        self.config.unlink()
        with self.assertRaises(ValueError):
            PROVISION.main()


if __name__ == "__main__":
    unittest.main()
