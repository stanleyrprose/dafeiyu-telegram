"""Phase V only: new owner-only calendar, autonomy and discovery integration tests."""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

try:
    from data.plugins.astrbot_plugin_dafeiyu_local_life.main import LocalLife
    from data.plugins.astrbot_plugin_dafeiyu_local_life.autonomy_state import AutonomyStore
    READY = True
except ModuleNotFoundError:
    READY = False


@unittest.skipUnless(READY, "Pinned AstrBot v4.29.4 runtime is required")
class AutonomyAstrBotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.plugin = object.__new__(LocalLife)
        self.plugin.umo = "telegram_owner:FriendMessage:12345"
        self.plugin.tz = "Asia/Shanghai"
        self.plugin.db = AutonomyStore(root / "state.sqlite3")
        self.plugin.db.initialize()
        self.plugin.notes_file = root / "notes.json"
        self.plugin.persona_file = root / "dafeiyu.md"
        self.plugin.persona_file.write_text("小鲸鱼，实话实说。", encoding="utf-8")
        self.plugin._notes_lock = asyncio.Lock()
        self.plugin._capture_lock = asyncio.Lock()
        self.plugin._outreach_lock = asyncio.Lock()
        self.plugin._background = set()
        self.plugin._last_capture = 0.0
        self.plugin._cron_ids = []
        self.plugin.context = SimpleNamespace(
            cron_manager=SimpleNamespace(list_jobs=AsyncMock(return_value=[
                SimpleNamespace(
                    name="dafeiyu-owner-reminders", cron_expression="* * * * *",
                    timezone="UTC",
                ),
                SimpleNamespace(
                    name="unrelated-other-owner-job",
                    cron_expression="* * * * *", timezone="UTC",
                ),
            ])),
            send_message=AsyncMock(return_value=True),
            get_using_provider_async=AsyncMock(return_value=None),
        )
        self.event = SimpleNamespace(
            unified_msg_origin=self.plugin.umo,
            plain_result=lambda value: value,
            get_message_str=lambda: "今天聊什么好？",
        )

    async def asyncTearDown(self):
        for task in self.plugin._background:
            task.cancel()
        self.temp.cleanup()

    async def responses(self, stream):
        return [response async for response in stream]

    async def test_calendar_command_creates_linked_reminder_and_snapshot(self):
        local = (datetime.now(timezone.utc) + timedelta(days=3)).astimezone(ZoneInfo(self.plugin.tz))
        date = local.strftime("%Y-%m-%d %H:%M")
        replies = await self.responses(
            self.plugin.calendar_event(self.event, f"{date} 60 项目会议")
        )
        self.assertIn("已创建日程 #1", replies[0])
        agenda = await self.responses(self.plugin.agenda(self.event))
        self.assertIn("项目会议", agenda[0])
        self.assertIn("dafeiyu-owner-reminders", agenda[0])
        self.assertNotIn("unrelated-other-owner-job", agenda[0])
        self.assertEqual(len(self.plugin.db.list_tasks("reminder")), 1)

    async def test_calendar_move_and_cancel_propagates(self):
        local = (datetime.now(timezone.utc) + timedelta(days=3)).astimezone(ZoneInfo(self.plugin.tz))
        before = local.strftime("%Y-%m-%d %H:%M")
        later = (local + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        await self.responses(self.plugin.calendar_event(self.event, f"{before} 60 开发评审"))
        moved = await self.responses(self.plugin.moveevent(self.event, f"1 {later} 90"))
        self.assertIn("同步更新", moved[0])
        deleted = await self.responses(self.plugin.eventcancel(self.event, 1))
        self.assertIn("已取消", deleted[0])
        self.assertFalse(self.plugin.db.list_tasks("reminder"))

    async def test_proactive_budget_no_duplicate(self):
        self.plugin.db.set_setting("proactive_enabled", "on")
        with patch("data.plugins.astrbot_plugin_dafeiyu_local_life.main.is_quiet_time",
                   return_value=False), patch(
                   "data.plugins.astrbot_plugin_dafeiyu_local_life.main.scheduled_contact_slot",
                   return_value=True):
            await self.plugin._proactive_tick()
            await self.plugin._proactive_tick()
        self.assertEqual(self.plugin.context.send_message.await_count, 1)

    async def test_private_todo_is_not_sent_to_proactive_generator(self):
        self.plugin.db.add_task("todo", "客户报价保密事项")
        self.plugin.db.set_setting("proactive_enabled", "on")
        model = SimpleNamespace(text_chat=AsyncMock(
            return_value=SimpleNamespace(completion_text="最近怎么样？"),
        ))
        self.plugin.context.get_using_provider_async = AsyncMock(return_value=model)
        with patch("data.plugins.astrbot_plugin_dafeiyu_local_life.main.is_quiet_time",
                   return_value=False), patch(
                   "data.plugins.astrbot_plugin_dafeiyu_local_life.main.scheduled_contact_slot",
                   return_value=True):
            await self.plugin._proactive_tick()
        prompt = model.text_chat.await_args.kwargs["prompt"]
        self.assertNotIn("报价", prompt)
        self.assertEqual(self.plugin.context.send_message.await_count, 1)

    async def test_explore_user_commands_and_daily_digest(self):
        added = await self.responses(self.plugin.explore(self.event, "add reddit 5G RAN"))
        self.assertIn("已追踪", added[0])
        await self.responses(self.plugin.explore(self.event, "on"))
        self.plugin._public_findings = AsyncMock(return_value=[{
            "source": "reddit",
            "topic": "5G RAN",
            "title": "Release note",
            "url": "https://www.reddit.com/r/LocalLLaMA/comments/abcde/",
            "snippet": "indexed",
        }])
        with patch("data.plugins.astrbot_plugin_dafeiyu_local_life.main.is_quiet_time",
                   return_value=False):
            await self.plugin._explore_daily()
        self.assertEqual(self.plugin.context.send_message.await_count, 1)
        self.assertFalse(self.plugin.db.unseen(
            "https://www.reddit.com/r/LocalLLaMA/comments/abcde/"
        ))

    async def test_when_livingmemory_active_legacy_auto_capture_is_off(self):
        self.event.get_message_str = lambda: "我喜欢传统回合制JRPG，我希望长期体验。"
        response = SimpleNamespace(role="assistant", completion_text="记住了。")
        with patch.dict(os.environ, {"DAFEIYU_LIVINGMEMORY_ENABLED": "true"}):
            await self.plugin.observe_response(self.event, response)
        self.assertFalse(self.plugin._background)
        self.assertFalse(self.plugin._load_notes())

    async def test_nonowner_cannot_create_event_or_enable_exploration(self):
        other = SimpleNamespace(unified_msg_origin="telegram_owner:FriendMessage:55555",
                                plain_result=lambda value: value)
        self.assertFalse(await self.responses(self.plugin.explore(other, "on")))
        self.assertFalse(await self.responses(self.plugin.calendar_event(other, "2099-11-01 09:00 60 事情")))
        self.assertFalse(self.plugin.db.list_topics())


if __name__ == "__main__":
    unittest.main()
