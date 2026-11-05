"""Local-only memory and rhythm. Adapted from dafeiyu life/memory/rhythm policy ideas."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr


@register(
    "astrbot_plugin_dafeiyu_local_life", "dafeiyu",
    "Private owner memory prompts and quiet daily rhythm", "1.3.0",
)
class LocalLife(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        owner = os.getenv("DAFEIYU_OWNER_USER_ID", "")
        if not owner.isascii() or not owner.isdecimal() or int(owner) <= 0:
            raise ValueError("缺少合法的 DAFEIYU_OWNER_USER_ID")
        self.umo = f"telegram_owner:FriendMessage:{owner}"
        self.notes_file = Path("/AstrBot/data/plugin_data/dafeiyu_local_life/notes.json")
        self.persona_file = Path("/AstrBot/persona/dafeiyu.md")
        self._notes_lock = asyncio.Lock()
        self._job_id = None

    def _is_owner(self, event: AstrMessageEvent) -> bool:
        return event.unified_msg_origin == self.umo

    def _load_notes(self) -> list[str]:
        if not self.notes_file.exists():
            return []
        raw = json.loads(self.notes_file.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
            raise ValueError("invalid local memory")
        return raw[:24]

    def _save_notes(self, notes: list[str]) -> None:
        path = self.notes_file
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name("." + path.name + "." + secrets.token_hex(6) + ".tmp")
        fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(notes, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    @filter.command("remember")
    async def remember(self, event: AstrMessageEvent, note: GreedyStr):
        if not self._is_owner(event):
            return
        entry = str(note).strip()
        if not entry or len(entry) > 400:
            yield event.plain_result("用法：/remember 要记住的事情（最多 400 字）")
            return
        async with self._notes_lock:
            records = self._load_notes()
            if entry not in records:
                records.append(entry)
                self._save_notes(records[-24:])
        yield event.plain_result("已经存入这台 Mac 的本地记忆。")

    @filter.command("memories")
    async def memories(self, event: AstrMessageEvent):
        if not self._is_owner(event):
            return
        records = self._load_notes()
        lines = [f"{idx + 1}. {value}" for idx, value in enumerate(records)]
        yield event.plain_result("\n".join(lines) if lines else "暂时没有单独保存的长期记忆。")

    @filter.command("forget")
    async def forget(self, event: AstrMessageEvent, number: int):
        if not self._is_owner(event):
            return
        async with self._notes_lock:
            records = self._load_notes()
            if not 1 <= number <= len(records):
                yield event.plain_result("序号不存在；发送 /memories 查看。")
                return
            records.pop(number - 1)
            self._save_notes(records)
        yield event.plain_result("已从本地记忆中删除这一条。")

    @filter.on_llm_request()
    async def inject(self, event: AstrMessageEvent, req) -> None:
        if not self._is_owner(event):
            return
        try:
            persona = self.persona_file.read_text(encoding="utf-8")[:12000]
            records = self._load_notes()
            memory = "\n".join("- " + text for text in records[-16:]) if records else "无额外持久笔记"
            block = persona + "\n\n【当前主人显式保存的本地记忆】\n" + memory
            req.system_prompt = (req.system_prompt or "") + "\n\n" + block
        except (OSError, ValueError) as exc:
            logger.warning("[local_life] 人格/记忆提示词暂不可用 (%s)", type(exc).__name__)

    @filter.on_astrbot_loaded()
    async def schedule(self):
        hour_text = os.getenv("DAFEIYU_RHYTHM_HOUR", "10").strip()
        tz = os.getenv("DAFEIYU_RHYTHM_TZ", "Asia/Shanghai")
        if not hour_text.isdecimal() or not 0 <= int(hour_text) <= 23:
            logger.warning("[local_life] 无效的节律小时，未安排主动通知")
            return
        manager = self.context.cron_manager
        for job in await manager.list_jobs("basic"):
            if job.name == "dafeiyu-owner-daily-rhythm":
                await manager.delete_job(job.job_id)
        job = await manager.add_basic_job(
            name="dafeiyu-owner-daily-rhythm",
            description="单用户自用每日关怀；只发送固定文本",
            cron_expression=f"0 {int(hour_text)} * * *",
            handler=self._daily_note,
            timezone=tz,
            persistent=False,
        )
        self._job_id = job.job_id

    async def _daily_note(self) -> None:
        provider = self.context.get_using_provider(self.umo)
        if getattr(provider, "busy", False):
            return
        try:
            delivered = await asyncio.wait_for(
                self.context.send_message(
                    self.umo, MessageChain().message("肥鱼来打个招呼：今天先挑一件最重要的小事做完，再慢慢安排其他事。"),
                ),
                timeout=15,
            )
            if not delivered:
                logger.warning("[local_life] Telegram 目标会话暂不可用，本轮跳过")
        except (asyncio.TimeoutError, OSError, RuntimeError) as exc:
            logger.warning("[local_life] 主动消息失败，跳过不重发 (%s)", type(exc).__name__)

    async def terminate(self):
        if self._job_id:
            await self.context.cron_manager.delete_job(self._job_id)
