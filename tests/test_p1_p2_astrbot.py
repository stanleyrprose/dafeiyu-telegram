"""AstrBot-backed P1/P2 regression: runs only inside pinned v4.29.4 container."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

try:
    from data.plugins.astrbot_plugin_dafeiyu_local_life.main import LocalLife
    from data.plugins.astrbot_plugin_dafeiyu_local_life.autonomy_state import AutonomyStore
    RUNTIME_AVAILABLE = True
except ModuleNotFoundError:
    RUNTIME_AVAILABLE = False


@unittest.skipUnless(RUNTIME_AVAILABLE, "Requires pinned AstrBot Docker runtime")
class LocalLifeAstrBotCases(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        directory = Path(self.temp.name)
        self.plugin = object.__new__(LocalLife)
        self.plugin.umo = "telegram_owner:FriendMessage:12345"
        self.plugin.tz = "Asia/Shanghai"
        self.plugin.db = AutonomyStore(directory / "state.sqlite3")
        self.plugin.db.initialize()
        self.plugin.notes_file = directory / "notes.json"
        self.plugin._notes_lock = asyncio.Lock()
        self.plugin._capture_lock = asyncio.Lock()
        self.plugin._background = set()
        self.plugin._last_capture = 0.0
        self.plugin._outreach_lock = asyncio.Lock()
        self.plugin._cron_ids = []
        self.plugin.context = SimpleNamespace(
            send_message=AsyncMock(return_value=True),
            get_using_provider_async=AsyncMock(return_value=None),
        )
        self.event = SimpleNamespace(
            unified_msg_origin=self.plugin.umo,
            plain_result=lambda value: value,
            get_message_str=lambda: "明天上午9点提醒我开会",
            stop_event=lambda: None,
        )

    async def asyncTearDown(self):
        for job in list(self.plugin._background):
            job.cancel()
        self.temp.cleanup()

    async def collect(self, agen):
        return [item async for item in agen]

    async def test_command_todo_roundtrip(self):
        replies = await self.collect(self.plugin.todo(self.event, "每天阅读30分钟"))
        self.assertIn("#1", replies[0])
        listed = await self.collect(self.plugin.todos(self.event))
        self.assertIn("每天阅读30分钟", listed[0])
        done = await self.collect(self.plugin.done(self.event, 1))
        self.assertIn("完成", done[0])
        self.assertFalse(self.plugin.db.list_tasks("todo"))

    async def test_natural_reminder_creates_id(self):
        replies = await self.collect(self.plugin.natural_remind(self.event))
        self.assertIn("提醒 #1", replies[0])
        self.assertEqual(len(self.plugin.db.list_tasks("reminder")), 1)

    async def test_reminder_delivery_claims_once(self):
        self.plugin.db.add_task("reminder", "到点喝水", "2000-01-01T00:00:00Z")
        await self.plugin._deliver_due()
        await self.plugin._deliver_due()
        self.assertEqual(self.plugin.context.send_message.await_count, 1)
        with self.plugin.db._connect() as db:
            row = db.execute("SELECT status FROM tasks").fetchone()
            self.assertEqual(row["status"], "sent")

    async def test_auto_memory_stores_only_literal_evidence(self):
        sentence = "我喜欢传统回合制JRPG，尤其是勇者斗恶龙。"
        answer = {"memory": "用户喜爱回合制JRPG",
                  "evidence": "我喜欢传统回合制JRPG",
                  "category": "preference",
                  "confidence": 0.96}
        llm = SimpleNamespace(
            text_chat=AsyncMock(return_value=SimpleNamespace(
                completion_text=json.dumps(answer, ensure_ascii=False)
            ))
        )
        self.plugin.context.get_using_provider_async = AsyncMock(return_value=llm)
        await self.plugin._extract_stable_memory(sentence)
        entries = self.plugin._load_notes()
        self.assertEqual(entries, ["偏好：我喜欢传统回合制JRPG"])

    async def test_owner_gate_does_not_mutate_for_nonowner(self):
        nonowner = SimpleNamespace(
            unified_msg_origin="telegram_owner:FriendMessage:67890",
            plain_result=lambda value: value,
        )
        self.assertFalse(await self.collect(self.plugin.todo(nonowner, "不应写入")))
        self.assertFalse(self.plugin.db.list_tasks())

    async def test_schedule_creates_minute_reminder_and_daily_nudge(self):
        self.plugin.context.cron_manager = SimpleNamespace(
            list_jobs=AsyncMock(return_value=[]),
            add_basic_job=AsyncMock(side_effect=[
                SimpleNamespace(job_id="r1"),
                SimpleNamespace(job_id="n1"),
                SimpleNamespace(job_id="p1"),
                SimpleNamespace(job_id="c1"),
            ]),
        )
        await self.plugin.schedule()
        self.assertEqual(self.plugin.context.cron_manager.add_basic_job.await_count, 4)
        args = self.plugin.context.cron_manager.add_basic_job.call_args_list
        self.assertEqual(args[0].kwargs["cron_expression"], "* * * * *")
        self.assertEqual(args[1].kwargs["cron_expression"], "0 10 * * *")
        self.assertEqual(args[2].kwargs["cron_expression"], "0,30 * * * *")
        self.assertEqual(args[3].kwargs["cron_expression"], "0 13 * * *")

    async def test_nudge_preview_needs_real_task(self):
        self.plugin.db.add_task("todo", "优先处理项目A")
        data = await self.collect(self.plugin.nudge(self.event, "now"))
        self.assertIn("优先处理项目A", data[0])


if __name__ == "__main__":
    unittest.main()
