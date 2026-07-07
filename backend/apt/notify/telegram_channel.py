import asyncio
import logging
import sqlite3

from telegram import Bot
from telegram.error import Forbidden, RetryAfter

from apt.domain.events import MatchEvent
from apt.domain.models import User
from apt.notify.format import telegram_message
from apt.repo.users import UserRepo

logger = logging.getLogger(__name__)


class TelegramChannel:
    name = "telegram"

    def __init__(self, conn: sqlite3.Connection, bot: Bot):
        self._conn = conn
        self._bot = bot

    def applicable(self, user: User) -> bool:
        return user.telegram_chat_id is not None

    async def deliver(self, user: User, event: MatchEvent) -> None:
        text = telegram_message(event)
        try:
            await self._send(user.telegram_chat_id, text)
        except Forbidden:
            # Blocked chats never succeed on retry; unlink instead.
            logger.info("telegram: chat %s blocked us, unlinking user %s", user.telegram_chat_id, user.id)
            UserRepo(self._conn).set_telegram_chat(user.id, None)

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
