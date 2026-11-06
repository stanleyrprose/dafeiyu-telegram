"""Phase V only: autonomy store, local calendar, public-index privacy regression."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin" / "astrbot_plugin_dafeiyu_local_life"
package = "dafeiyu_autonomy_pure"
if package not in sys.modules:
    group = types.ModuleType(package)
    group.__path__ = [str(PLUGIN)]
    sys.modules[package] = group


def load(name):
    key = package + "." + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, PLUGIN / (name + ".py"))
    obj = importlib.util.module_from_spec(spec)
    sys.modules[key] = obj
    spec.loader.exec_module(obj)
    return obj


state = load("state")
store_module = load("autonomy_state")
calendar = load("calendar_policy")
social = load("social_discovery")
config_path = ROOT / "scripts" / "prepare_livingmemory.py"
spec = importlib.util.spec_from_file_location("dafeiyu_vendor_setup", config_path)
vendor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor)


class CalendarStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = store_module.AutonomyStore(Path(self.temp.name) / "state.db")
        self.db.initialize()
        self.future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.finish = (datetime.now(timezone.utc) + timedelta(days=2, hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def tearDown(self):
        self.temp.cleanup()

    def test_event_and_reminder_created_in_one_transaction(self):
        number, conflicts = self.db.add_event("项目会议", self.future, self.finish)
        self.assertEqual(conflicts, 0)
        self.assertEqual(len(self.db.list_events(state.utc_now(), self.finish)), 1)
        tasks = self.db.list_tasks("reminder")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["due_utc"], self.future)
        self.assertEqual(self.db.get_event(number)["reminder_id"], tasks[0]["id"])

    def test_cancel_event_also_cancels_reminder(self):
        number, _ = self.db.add_event("回顾项目", self.future, self.finish)
        self.assertTrue(self.db.cancel_event(number))
        self.assertFalse(self.db.list_tasks("reminder"))
        self.assertIsNone(self.db.get_event(number))

    def test_move_event_updates_pending_reminder(self):
        number, _ = self.db.add_event("周会", self.future, self.finish)
        new_start = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_end = (datetime.now(timezone.utc) + timedelta(days=3, hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertTrue(self.db.update_event(number, new_start, new_end))
        self.assertEqual(self.db.list_tasks("reminder")[0]["due_utc"], new_start)
        self.assertEqual(self.db.get_event(number)["start_utc"], new_start)

    def test_linked_reminder_cancel_updates_event(self):
        number, _ = self.db.add_event("完成演示", self.future, self.finish)
        reminder = self.db.list_tasks("reminder")[0]
        self.assertTrue(self.db.change_task(reminder["id"], "cancelled", ("pending",)))
        self.assertIsNone(self.db.get_event(number))

    def test_outreach_shared_budget_and_no_unanswered_spam(self):
        self.assertTrue(self.db.claim_outreach("2026-11-06", "proactive"))
        self.db.finish_outreach("2026-11-06", True)
        self.assertFalse(self.db.claim_outreach("2026-11-06", "community"))
        self.assertFalse(self.db.claim_outreach("2026-11-07", "community"))
        self.db.record_owner_reply()
        self.assertTrue(self.db.claim_outreach("2026-11-07", "community"))
        self.db.finish_outreach("2026-11-07", False)
        self.assertFalse(self.db.claim_outreach("2026-11-08", "proactive"))
        self.db.record_owner_reply()
        self.assertTrue(self.db.claim_outreach("2026-11-08", "proactive"))

    def test_seen_links_stores_only_hash_and_expires(self):
        link = "https://www.reddit.com/r/LocalLLaMA/comments/abcde/"
        self.assertTrue(self.db.unseen(link))
        self.db.remember_links("reddit", [link])
        self.assertFalse(self.db.unseen(link))
        with self.db._connect() as con:
            row = con.execute("SELECT digest FROM discovery_seen").fetchone()
        self.assertEqual(len(row[0]), 64)
        self.assertNotIn("reddit", row[0])

    def test_reenabling_topic_respects_limit(self):
        first = self.db.add_topic("x", "topic alpha")
        self.assertTrue(self.db.pause_topic(first))
        for number in range(12):
            self.db.add_topic("reddit", f"topic new {number}")
        with self.assertRaises(ValueError):
            self.db.add_topic("x", "topic alpha")

    def test_topics_are_bounded(self):
        self.assertEqual(self.db.add_topic("x", "AI agents"), 1)
        self.assertEqual(self.db.add_topic("x", "AI agents"), 1)
        self.assertEqual(len(self.db.list_topics()), 1)


class PolicyTests(unittest.TestCase):
    def test_explicit_calendar_no_guessing(self):
        now = datetime(2026, 11, 6, tzinfo=timezone.utc)
        start, end, title = calendar.event_interval(
            "2026-11-09 09:00 60 项目会议", "Asia/Yangon", now,
        )
        self.assertEqual(start, "2026-11-09T02:30:00Z")
        self.assertEqual(end, "2026-11-09T03:30:00Z")
        self.assertEqual(title, "项目会议")
        with self.assertRaises(ValueError):
            calendar.event_interval("下周开会", "Asia/Yangon", now)

    def test_quiet_hours_and_daily_slot(self):
        quiet = datetime(2026, 11, 6, 18, tzinfo=timezone.utc)
        self.assertTrue(calendar.is_quiet_time(quiet, "Asia/Yangon"))
        midday = datetime(2026, 11, 6, 6, tzinfo=timezone.utc)
        self.assertFalse(calendar.is_quiet_time(midday, "Asia/Yangon"))
        self.assertEqual(calendar.scheduled_contact_slot(midday, "Asia/Yangon", "a"),
                         calendar.scheduled_contact_slot(midday, "Asia/Yangon", "a"))

    def test_x_reddit_url_only_not_login_or_offsite(self):
        self.assertEqual(
            social.canonical_public_post("x", "https://x.com/example/status/123456789?s=20"),
            "https://x.com/example/status/123456789",
        )
        self.assertEqual(
            social.canonical_public_post(
                "reddit", "https://www.reddit.com/r/LocalLLaMA/comments/abcde/a_title/?share=1"
            ),
            "https://www.reddit.com/r/LocalLLaMA/comments/abcde/",
        )
        for link in ("http://x.com/user/status/123456789",
                     "https://x.com.evil.org/user/status/123456789",
                     "https://reddit.com/r/community/",
                     "https://localhost/r/ai/comments/abcde/"):
            self.assertIsNone(social.canonical_public_post("reddit", link))

    def test_never_send_private_queries_to_third_party(self):
        for query in ["我的护照号123456789", "客户报价", "user@example.com", "银行卡"]:
            with self.assertRaises(ValueError):
                social.safe_topic(query)


class VendorConfigTests(unittest.TestCase):
    def test_embedding_provider_is_private_and_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "cmd_config.json").write_text(
                json.dumps({"provider": [{"id": "dafeiyu_siwc", "type": "dafeiyu_siwc"}]}),
                encoding="utf-8",
            )
            vendor.configure(path)
            config = json.loads((path / "cmd_config.json").read_text())
            self.assertEqual(config["provider"][0]["id"], "dafeiyu_siwc")
            self.assertEqual(config["provider"][1]["id"], "dafeiyu_bge_m3")
            self.assertIn("host.docker.internal:11434", config["provider"][1]["embedding_api_base"])
            self.assertEqual(config["provider"][1]["embedding_dimensions"], 1024)
            plugin = json.loads(
                (path / "config" / "astrbot_plugin_livingmemory_config.json").read_text()
            )
            self.assertEqual(plugin["provider_settings"]["llm_stream_mode"], "always")
            self.assertEqual(plugin["filtering_settings"]["memory_scope_mode"], "session")
            self.assertFalse(plugin["agent_tools"]["enable_recall_tool"])

    def test_rollback_keeps_user_memory_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "plugins" / "astrbot_plugin_livingmemory"
            path.mkdir(parents=True)
            (path / "main.py").write_text("example", encoding="utf-8")
            data = root / "plugin_data" / "astrbot_plugin_livingmemory"
            data.mkdir(parents=True)
            (data / "note.txt").write_text("retained", encoding="utf-8")
            vendor.disable_for_rollback(root)
            self.assertFalse(path.exists())
            self.assertTrue((root / "vendor_disabled_plugins" /
                             "astrbot_plugin_livingmemory-2.9.1" / "main.py").is_file())
            self.assertEqual((data / "note.txt").read_text(), "retained")


if __name__ == "__main__":
    unittest.main()
