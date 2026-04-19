"""Tests for _escape_preview — the Telegram-safe HTML escaper/truncator."""

import pytest

from app.bot.routers.concierge import _TELEGRAM_SAFE_LIMIT, _escape_preview


def _assert_no_broken_entity(s: str) -> None:
    """Fail if the string contains an `&...` sequence without a closing `;`."""
    amp = s.rfind("&")
    if amp == -1:
        return
    tail = s[amp:]
    assert ";" in tail, f"broken entity at tail: {tail!r}"


class TestEscapePreview:
    def test_short_text_passes_through(self):
        assert _escape_preview("hello") == "hello"

    def test_escapes_angle_brackets(self):
        assert _escape_preview("<b>") == "&lt;b&gt;"

    def test_result_fits_telegram_limit(self):
        # Heavy expansion: every char becomes &amp; (×5)
        escaped = _escape_preview("&" * 10_000)
        assert len(escaped) <= _TELEGRAM_SAFE_LIMIT
        assert escaped.endswith("…")

    def test_no_broken_entity_on_amp_boundary(self):
        # Craft input where naive slice would land inside `&amp;`.
        result = _escape_preview("&" * 10_000)
        _assert_no_broken_entity(result)

    def test_no_broken_entity_on_mixed_entities(self):
        # Mix of `<`, `>`, `&`, `"` — all escape differently.
        mixed = ('&<>"' * 2000)
        result = _escape_preview(mixed)
        _assert_no_broken_entity(result)
        assert len(result) <= _TELEGRAM_SAFE_LIMIT

    def test_plain_text_under_limit_unchanged(self):
        text = "a" * 1000
        assert _escape_preview(text) == text

    def test_exactly_at_limit_not_truncated(self):
        # No HTML-special chars → escape is a no-op.
        text = "x" * _TELEGRAM_SAFE_LIMIT
        assert _escape_preview(text) == text

    def test_unicode_passes_through(self):
        text = "Привет, мир! 🌍"
        assert _escape_preview(text) == text
