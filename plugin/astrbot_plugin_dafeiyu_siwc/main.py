"""Private Telegram adapter and SIWC registration: no core patches."""
from __future__ import annotations

import os

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ApplicationHandlerStop, TypeHandler

from astrbot.api.platform import register_platform_adapter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter

# Import at plugin load time, before AstrBot's ProviderManager.initialize().
from . import provider as provider_module


@register_platform_adapter(
    "telegram_owner",
    "Telegram (private owner only)",
    default_config_tmpl={
        "id": "telegram_owner",
        "type": "telegram_owner",
        "enable": False,
        "telegram_token": "",
        "start_message": "你好，肥鱼在这儿。",
        "telegram_api_base_url": "https://api.telegram.org/bot",
        "telegram_file_base_url": "https://api.telegram.org/file/bot",
        "telegram_command_register": True,
        "telegram_command_auto_refresh": True,
        "telegram_command_register_interval": 300,
        "telegram_polling_restart_delay": 5.0,
    },
)
class OwnerTelegramAdapter(TelegramPlatformAdapter):
    """Use Telegram's native polling client with a pre-dispatch owner gate."""

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue):
        raw = os.environ.get("DAFEIYU_OWNER_USER_ID", "").strip()
        if not raw.isascii() or not raw.isdecimal() or int(raw) <= 0:
            raise ValueError("DAFEIYU_OWNER_USER_ID 必须是非零的 Telegram 数字 User ID")
        self.owner_id = int(raw)
        super().__init__(platform_config, platform_settings, event_queue)

    def _build_application(self) -> None:
        super()._build_application()
        self.application.add_handler(TypeHandler(Update, self._owner_gate), group=-100)

    def _allowed(self, update: Update) -> bool:
        user, chat = update.effective_user, update.effective_chat
        return bool(
            user and chat
            and chat.type == ChatType.PRIVATE
            and user.id == self.owner_id
            and chat.id == self.owner_id
        )

    async def _owner_gate(self, update: Update, context) -> None:
        if not self._allowed(update):
            raise ApplicationHandlerStop

    async def message_handler(self, update: Update, context) -> None:
        if not self._allowed(update):
            return
        if update.message and not update.message.text:
            await context.bot.send_message(
                chat_id=self.owner_id,
                text="当前版本仅支持文字对话。",
            )
            return
        await super().message_handler(update, context)


@register(
    "astrbot_plugin_dafeiyu_siwc",
    "dafeiyu",
    "SIWC text provider and owner-only Telegram adapter",
    "1.3.0",
)
class DafeiyuSIWCPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
