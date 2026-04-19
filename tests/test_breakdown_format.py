"""Tests for the human-readable breakdown renderer."""

from datetime import datetime, timedelta

import pytest

from app.bot.breakdown_format import format_breakdown


def _make_task(**overrides):
    base = {
        "title": "Выгул собаки",
        "description": "Выгулять собаку жильца",
        "category": "pet_walk",
        "datetime": None,
        "time_range": None,
        "duration_minutes": None,
        "recurrence": "none",
        "location": None,
        "participants": [],
        "priority": "normal",
        "source_fragment": "выгулять собаку",
        "confidence": "high",
        "needs_clarification": False,
        "clarification_questions": [],
    }
    base.update(overrides)
    return base


class TestBasicShape:
    def test_empty_payload_has_friendly_message(self):
        result = format_breakdown({})
        assert "Пустой разбор" in result

    def test_all_empty_arrays(self):
        result = format_breakdown({
            "tasks": [],
            "unclear_items": [],
            "ignored_context": "",
        })
        assert "Пустой разбор" in result

    def test_one_task_happy_path(self):
        payload = {
            "tasks": [_make_task(title="Груминг", category="grooming")],
            "unclear_items": [],
            "ignored_context": "",
        }
        out = format_breakdown(payload)
        assert "Задач: 1" in out
        assert "Груминг" in out
        assert "✂️" in out

    def test_multiple_tasks_numbered(self):
        payload = {
            "tasks": [
                _make_task(title="Первая", category="fitness"),
                _make_task(title="Вторая", category="pool"),
            ],
        }
        out = format_breakdown(payload)
        assert "Задач: 2" in out
        assert "1." in out and "2." in out
        assert "🏋" in out and "🏊" in out


class TestCategoryIcons:
    @pytest.mark.parametrize("category,icon", [
        ("fitness", "🏋"),
        ("pool", "🏊"),
        ("grooming", "✂️"),
        ("pet_walk", "🐕"),
        ("parking", "🚗"),
        ("guest", "🚪"),
        ("housekeeping", "🧹"),
        ("meeting", "🤝"),
        ("delivery", "📦"),
        ("maintenance", "🔧"),
        ("booking", "📅"),
        ("complaint", "📢"),
        ("info", "ℹ️"),
        ("other", "📋"),
    ])
    def test_known_category_icon(self, category, icon):
        payload = {"tasks": [_make_task(category=category)]}
        assert icon in format_breakdown(payload)

    def test_unknown_category_falls_back_to_other(self):
        payload = {"tasks": [_make_task(category="invented")]}
        assert "📋" in format_breakdown(payload)


class TestPriority:
    def test_high_priority_shown(self):
        payload = {"tasks": [_make_task(priority="high")]}
        assert "срочно" in format_breakdown(payload)

    def test_normal_priority_hidden(self):
        payload = {"tasks": [_make_task(priority="normal")]}
        out = format_breakdown(payload)
        assert "срочно" not in out

    def test_low_priority_shown(self):
        payload = {"tasks": [_make_task(priority="low")]}
        assert "не срочно" in format_breakdown(payload)


class TestTimeFormatting:
    def test_today_datetime_says_today(self):
        today = datetime.now().astimezone().replace(hour=15, minute=0, second=0, microsecond=0)
        payload = {"tasks": [_make_task(datetime=today.isoformat())]}
        out = format_breakdown(payload)
        assert "сегодня" in out
        assert "15:00" in out

    def test_tomorrow_datetime_says_tomorrow(self):
        tomorrow = (datetime.now().astimezone() + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0,
        )
        payload = {"tasks": [_make_task(datetime=tomorrow.isoformat())]}
        out = format_breakdown(payload)
        assert "завтра" in out
        assert "08:00" in out

    def test_time_range_only(self):
        payload = {"tasks": [_make_task(datetime=None, time_range="morning")]}
        assert "утром" in format_breakdown(payload)

    def test_invalid_datetime_passes_through(self):
        payload = {"tasks": [_make_task(datetime="not-an-iso-string")]}
        out = format_breakdown(payload)
        assert "not-an-iso-string" in out


class TestOptionalFields:
    def test_location_shown(self):
        payload = {"tasks": [_make_task(location="фитнес-студия")]}
        assert "📍 фитнес-студия" in format_breakdown(payload)

    def test_participants_joined(self):
        payload = {"tasks": [_make_task(participants=["Николай", "Анна"])]}
        out = format_breakdown(payload)
        assert "👥 Николай, Анна" in out

    def test_empty_participants_hidden(self):
        payload = {"tasks": [_make_task(participants=[])]}
        assert "👥" not in format_breakdown(payload)

    def test_duration_shown(self):
        payload = {"tasks": [_make_task(duration_minutes=60)]}
        assert "60 мин" in format_breakdown(payload)

    def test_zero_duration_hidden(self):
        payload = {"tasks": [_make_task(duration_minutes=0)]}
        assert "мин" not in format_breakdown(payload)

    def test_daily_recurrence(self):
        payload = {"tasks": [_make_task(recurrence="daily")]}
        assert "ежедневно" in format_breakdown(payload)

    def test_none_recurrence_hidden(self):
        payload = {"tasks": [_make_task(recurrence="none")]}
        assert "🔁" not in format_breakdown(payload)

    def test_confidence_medium_shown(self):
        payload = {"tasks": [_make_task(confidence="medium")]}
        assert "частично ясно" in format_breakdown(payload)

    def test_confidence_high_hidden(self):
        payload = {"tasks": [_make_task(confidence="high")]}
        assert "частично ясно" not in format_breakdown(payload)


class TestQuestions:
    def test_clarification_questions_listed(self):
        payload = {"tasks": [_make_task(
            needs_clarification=True,
            clarification_questions=["Во сколько?", "Где встреча?"],
        )]}
        out = format_breakdown(payload)
        assert "Нужно уточнить" in out
        assert "Во сколько?" in out
        assert "Где встреча?" in out

    def test_needs_clarification_without_questions(self):
        payload = {"tasks": [_make_task(
            needs_clarification=True,
            clarification_questions=[],
        )]}
        assert "детали у жильца" in format_breakdown(payload)


class TestUnclearAndIgnored:
    def test_unclear_items_block(self):
        payload = {
            "tasks": [],
            "unclear_items": [
                {"fragment": "эээ", "reason": "мычание", "question": "что имелось в виду?"},
            ],
        }
        out = format_breakdown(payload)
        assert "Непонятные фрагменты" in out
        assert "«эээ»" in out
        assert "что имелось в виду?" in out

    def test_ignored_context_shown(self):
        payload = {
            "tasks": [_make_task()],
            "ignored_context": "Приветствие — не задача.",
        }
        assert "Контекст без задач" in format_breakdown(payload)
        assert "Приветствие — не задача" in format_breakdown(payload)


class TestHtmlSafety:
    def test_escapes_angle_brackets_in_title(self):
        payload = {"tasks": [_make_task(title="<script>alert()</script>")]}
        out = format_breakdown(payload)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_escapes_ampersands_in_quote(self):
        payload = {"tasks": [_make_task(source_fragment="Иван & Петров")]}
        assert "Иван &amp; Петров" in format_breakdown(payload)

    def test_long_source_fragment_trimmed(self):
        payload = {"tasks": [_make_task(source_fragment="x" * 500)]}
        out = format_breakdown(payload)
        assert "…" in out
        # Ensure the quote is bounded (within Telegram safe limits).
        assert "x" * 500 not in out


class TestLengthCap:
    def test_big_payload_truncated(self):
        # 50 tasks → definitely over 3800 chars.
        tasks = [_make_task(title=f"Задача номер {i}") for i in range(50)]
        out = format_breakdown({"tasks": tasks}, max_chars=1000)
        assert len(out) <= 1000
        assert out.endswith("…")

    def test_no_truncation_when_fits(self):
        payload = {"tasks": [_make_task()]}
        out = format_breakdown(payload, max_chars=10_000)
        assert not out.endswith("…")


class TestShapeTolerance:
    def test_non_list_tasks_key_handled(self):
        out = format_breakdown({"tasks": "not a list"})
        assert "Пустой разбор" in out

    def test_non_dict_task_skipped(self):
        payload = {"tasks": [_make_task(), "not-a-dict", _make_task(title="Вторая")]}
        out = format_breakdown(payload)
        # One string task skipped, two proper tasks formatted.
        assert "Задач: 3" in out  # count reflects the raw input length
        assert "Вторая" in out
