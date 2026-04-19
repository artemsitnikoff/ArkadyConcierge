import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.logging_config import new_trace_id, reset_trace_id, set_trace_id

logger = logging.getLogger("concierge")


class TraceIdMiddleware(BaseMiddleware):
    """Bind a per-update trace_id so every log line during an update handler
    carries the same ID. Prefer Telegram's own update_id when available.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update_id = data.get("event_update") and getattr(
            data["event_update"], "update_id", None,
        )
        trace_id = f"tg-{update_id}" if update_id else new_trace_id(prefix="tg-")
        token = set_trace_id(trace_id)
        try:
            return await handler(event, data)
        finally:
            reset_trace_id(token)


class ErrorMiddleware(BaseMiddleware):
    """Catch unhandled exceptions and reply with a generic message."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except asyncio.CancelledError:
            # Shutdown signal — propagate so polling can terminate cleanly.
            # Logging + replying would mislead operators and can race with a
            # closed bot session.
            raise
        except Exception:
            chat_id: Any = "?"
            user_id: Any = "?"
            if isinstance(event, Message):
                chat_id = event.chat.id
                user_id = event.from_user.id if event.from_user else "?"
            elif isinstance(event, CallbackQuery):
                chat_id = event.message.chat.id if event.message else "?"
                user_id = event.from_user.id if event.from_user else "?"

            logger.error(
                "Unhandled error in chat=%s user=%s", chat_id, user_id, exc_info=True,
            )
            try:
                if isinstance(event, Message):
                    await event.reply("❌ Произошла ошибка. Попробуй ещё раз.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Произошла ошибка", show_alert=True)
            except Exception:
                pass
            return None


class AccessMiddleware(BaseMiddleware):
    """Gate the bot by ALLOWED_USERS. Empty set = everyone allowed.

    Applied to both messages and callback queries.
    """

    def __init__(self) -> None:
        self._allowed: set[int] = settings.allowed_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self._allowed:
            return await handler(event, data)

        user_id: int | None = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if user_id is None or user_id not in self._allowed:
            logger.info("Access denied: user_id=%s", user_id)
            if isinstance(event, Message):
                await event.reply("⛔️ Доступ закрыт.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔️ Доступ закрыт", show_alert=True)
            return None

        return await handler(event, data)
