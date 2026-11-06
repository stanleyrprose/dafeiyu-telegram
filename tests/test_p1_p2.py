"""Targeted P1/P2 regression specification. Run only in Phase V.

No network, Docker, Telegram credentials or AstrBot runtime is required.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "plugin" / "astrbot_plugin_dafeiyu_local_life"


def load_pure(name):
    spec = importlib.util.spec_from_file_location("dafeiyu_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state = load_pure("state")
policy = load_pure("policy")
web = load_pure("web_read")


class TaskPersistenceCases(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "new-state.sqlite3"
        self.store = state.LifeStore(self.path)
        self.store.initialize()

    def tearDown(self):
        self.directory.cleanup()

    def test_todo_survives_reopen_and_can_complete(self):
        number = self.store.add_task("todo", "Finish one milestone")
        self.assertEqual(len(state.LifeStore(self.path).list_tasks("todo")), 1)
        self.assertTrue(self.store.change_task(number, "done", ("pending",)))
        self.assertFalse(self.store.list_tasks("todo"))

    def test_due_claim_is_atomic_and_not_automatically_resent(self):
        due = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        number = self.store.add_task("reminder", "Call friend", due)
        self.assertEqual([t["id"] for t in self.store.claim_due(state.utc_now())], [number])
        self.assertEqual(self.store.claim_due(state.utc_now()), [])
        state.LifeStore(self.path).recover_unknown()
        self.assertEqual(self.store.list_tasks("reminder")[0]["status"], "unknown")
        self.assertEqual(self.store.claim_due(state.utc_now()), [])
        self.assertTrue(self.store.change_task(number, "pending", ("unknown",)))
        self.assertEqual(len(self.store.claim_due(state.utc_now())), 1)
        self.store.record_delivery(number, succeeded=True)
        self.assertFalse(self.store.list_tasks("reminder"))

    def test_reminder_cannot_be_completed_twice(self):
        due = (datetime.now(timezone.utc) + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        number = self.store.add_task("reminder", "Take a break", due)
        self.assertTrue(self.store.change_task(number, "cancelled", ("pending",)))
        self.assertFalse(self.store.change_task(number, "pending", ("unknown",)))

    def test_only_one_daily_nudge_per_day(self):
        self.assertTrue(self.store.claim_nudge("2026-11-06"))
        self.assertFalse(state.LifeStore(self.path).claim_nudge("2026-11-06"))
        self.store.finish_nudge("2026-11-06", True)

    def test_activity_survives_restart(self):
        now = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)
        self.store.note_interaction(now)
        self.store.note_interaction(now)
        summary = state.LifeStore(self.path).activity_summary("2026-11-05")
        self.assertEqual(summary["messages"], 2)
        self.assertEqual(summary["active_days"], 1)


class ReminderParserCases(unittest.TestCase):
    NOW = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)

    def test_absolute_time_timezone(self):
        due, description = policy.parse_reminder(
            "2026-11-06 09:00 开会", "Asia/Yangon", self.NOW
        )
        self.assertEqual(due, "2026-11-06T02:30:00Z")
        self.assertEqual(description, "开会")

    def test_natural_tomorrow_morning(self):
        due, description = policy.parse_reminder(
            "明天上午9点提醒我开会", "Asia/Shanghai", self.NOW
        )
        self.assertEqual(due, "2026-11-06T01:00:00Z")
        self.assertEqual(description, "开会")

    def test_relative_minutes(self):
        due, _ = policy.parse_reminder("10分钟后提醒我喝水", "Asia/Shanghai", self.NOW)
        self.assertEqual(due, "2026-11-05T02:10:00Z")

    def test_missing_time_is_not_silent_default(self):
        with self.assertRaises(ValueError):
            policy.parse_reminder("明天提醒我开会", "Asia/Yangon", self.NOW)

    def test_past_time_is_rejected(self):
        with self.assertRaises(ValueError):
            policy.parse_reminder("2026-11-04 09:00 开会", "Asia/Yangon", self.NOW)


class MemoryPolicyCases(unittest.TestCase):
    def test_literal_evidence_low_risk_fact(self):
        source = "我喜欢传统回合制JRPG，尤其是勇者斗恶龙。"
        self.assertTrue(policy.safe_memory(
            "用户偏好传统回合制JRPG", "我喜欢传统回合制JRPG",
            source, "preference", 0.95
        ))

    def test_rejects_unsubstantiated_fact(self):
        self.assertFalse(policy.safe_memory(
            "用户喜欢冒险", "我喜欢冒险", "我喜欢茶",
            "preference", 0.99
        ))

    def test_rejects_sensitive_or_low_confidence(self):
        self.assertFalse(policy.safe_memory(
            "用户的护照号在此", "我的护照号",
            "我的护照号是示例", "preference", 0.99
        ))
        self.assertFalse(policy.safe_memory(
            "用户喜欢吉他", "我喜欢吉他",
            "我喜欢吉他", "preference", 0.65
        ))

    def test_nudge_requires_real_tasks_and_respects_recent_activity(self):
        now = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)
        task = {"id": 1, "kind": "todo", "status": "pending", "text": "看书",
                "due_utc": None}
        empty = {"messages": 0, "active_days": 0, "last_utc": None}
        self.assertIsNone(policy.daily_nudge([], empty, now, "Asia/Shanghai"))
        self.assertIn("看书", policy.daily_nudge([task], empty, now, "Asia/Shanghai"))
        just_talked = {**empty, "last_utc": "2026-11-05T01:00:00Z"}
        self.assertIsNone(policy.daily_nudge([task], just_talked, now, "Asia/Shanghai"))


class ReadOnlyWebCases(unittest.TestCase):
    def test_rejects_internal_and_credentials(self):
        for url in [
            "http://example.com", "https://localhost/",
            "https://127.0.0.1/", "https://printer.local/",
            "https://user:password@example.com/", "https://example.com:8443/",
            "file:///etc/passwd",
        ]:
            with self.subTest(url=url), self.assertRaises(web.UnsafeURL):
                web._public_target(url)

    def test_rejects_private_dns_target(self):
        with patch.object(web.socket, "getaddrinfo", return_value=[
            (2, 1, 6, "", ("10.0.0.5", 443)),
        ]):
            with self.assertRaises(web.UnsafeURL):
                web._public_target("https://example.com/news")

    def test_public_dns_is_pinned_without_network_request(self):
        with patch.object(web.socket, "getaddrinfo", return_value=[
            (2, 1, 6, "", ("8.8.8.8", 443)),
        ]):
            self.assertEqual(
                web._public_target("https://example.com/report?a=1"),
                ("example.com", "8.8.8.8", "/report?a=1"),
            )


if __name__ == "__main__":
    unittest.main()
