"""Tests for aiogram middlewares."""

import asyncio

import pytest
from aiogram.types import Chat, Message, User

from app.bot.middlewares import ErrorMiddleware


def _make_message() -> Message:
    # Bypass aiogram validation — model_construct sets fields without checks.
    return Message.model_construct(
        message_id=1,
        date=0,
        chat=Chat(id=123, type="private"),
        from_user=User(id=42, is_bot=False, first_name="t"),
        text="hi",
    )


class TestErrorMiddleware:
    async def test_cancelled_error_propagates(self):
        """On shutdown, CancelledError must bubble up so polling stops cleanly."""
        mw = ErrorMiddleware()
        message = _make_message()

        async def handler(event, data):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await mw(handler, message, {})

    async def test_regular_exception_is_swallowed(self):
        """Ordinary errors are caught, logged, and the user is replied to."""
        mw = ErrorMiddleware()
        message = _make_message()
        replies: list[str] = []

        async def fake_reply(text: str, *_a, **_kw):
            replies.append(text)

        # Message is a frozen pydantic model — bypass the validator to inject
        # a stub method.
        object.__setattr__(message, "reply", fake_reply)

        async def handler(event, data):
            raise RuntimeError("boom")

        # Must NOT raise — the middleware is the error boundary.
        result = await mw(handler, message, {})
        assert result is None
        assert replies and "ошибка" in replies[0].lower()

    async def test_happy_path_returns_handler_value(self):
        mw = ErrorMiddleware()
        message = _make_message()

        async def handler(event, data):
            return "ok"

        assert await mw(handler, message, {}) == "ok"
