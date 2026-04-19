"""Human-readable Russian rendering of a concierge breakdown JSON.

The JSON schema comes from `prompts/concierge_breakdown.md` and has three
top-level keys: `tasks` (list), `unclear_items` (list), `ignored_context`
(string). Missing or null fields are tolerated — AI sometimes omits
them on simple inputs.

Output is Telegram-flavoured HTML (bold/italic only) with all
AI-controlled strings HTML-escaped. Safe to send with `parse_mode=HTML`.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

CATEGORY_ICONS: dict[str, str] = {
    "fitness": "🏋",
    "pool": "🏊",
    "grooming": "✂️",
    "pet_walk": "🐕",
    "parking": "🚗",
    "guest": "🚪",
    "housekeeping": "🧹",
    "meeting": "🤝",
    "delivery": "📦",
    "maintenance": "🔧",
    "booking": "📅",
    "complaint": "📢",
    "info": "ℹ️",
    "other": "📋",
}

TIME_RANGE_RU: dict[str, str] = {
    "morning": "утром",
    "afternoon": "днём",
    "evening": "вечером",
    "night": "ночью",
}

PRIORITY_LABEL: dict[str, str] = {
    "high": "🔴 срочно",
    "low": "⚪ не срочно",
}

RECURRENCE_RU: dict[str, str] = {
    "daily": "ежедневно",
    "weekly": "еженедельно",
}

CONFIDENCE_LABEL: dict[str, str] = {
    "medium": "⚠️ частично ясно",
    "low": "⚠️ мало данных",
}

_MAX_QUOTE_CHARS = 200


def _format_when(dt_str: str | None, time_range: str | None) -> str:
    """Combine ISO datetime + time_range into a short Russian string."""
    pieces: list[str] = []
    if dt_str:
        try:
            dt = datetime.fromisoformat(dt_str)
            now = datetime.now().astimezone()
            dt_local = dt.astimezone(now.tzinfo) if dt.tzinfo else dt
            delta_days = (dt_local.date() - now.date()).days
            if delta_days == 0:
                pieces.append(f"сегодня {dt_local.strftime('%H:%M')}")
            elif delta_days == 1:
                pieces.append(f"завтра {dt_local.strftime('%H:%M')}")
            elif 2 <= delta_days <= 6:
                pieces.append(dt_local.strftime("%d.%m %H:%M"))
            else:
                pieces.append(dt_local.strftime("%d.%m.%Y %H:%M"))
        except ValueError:
            pieces.append(dt_str)
    elif time_range and TIME_RANGE_RU.get(time_range):
        pieces.append(TIME_RANGE_RU[time_range])
    return ", ".join(pieces)


def _trim_quote(text: str) -> str:
    """Cap long source fragments to keep the preview compact."""
    text = text.strip()
    if len(text) <= _MAX_QUOTE_CHARS:
        return text
    return text[: _MAX_QUOTE_CHARS - 1].rstrip() + "…"


def _format_task(index: int, task: dict[str, Any]) -> list[str]:
    title = escape(str(task.get("title") or "без названия"))
    category = str(task.get("category") or "other")
    icon = CATEGORY_ICONS.get(category, "📋")
    priority = str(task.get("priority") or "normal")

    header = f"<b>{index}. {icon} {title}</b>"
    prio = PRIORITY_LABEL.get(priority)
    if prio:
        header += f"  <i>{prio}</i>"

    lines: list[str] = [header]

    when = _format_when(task.get("datetime"), task.get("time_range"))
    if when:
        lines.append(f"   🗓 {escape(when)}")

    duration = task.get("duration_minutes")
    if isinstance(duration, (int, float)) and duration > 0:
        lines.append(f"   ⏱ {int(duration)} мин")

    recurrence = task.get("recurrence")
    if recurrence and recurrence != "none":
        rec_ru = RECURRENCE_RU.get(str(recurrence), str(recurrence))
        lines.append(f"   🔁 {escape(rec_ru)}")

    location = task.get("location")
    if location:
        lines.append(f"   📍 {escape(str(location))}")

    participants = task.get("participants") or []
    if participants:
        joined = ", ".join(str(p) for p in participants if p)
        if joined:
            lines.append(f"   👥 {escape(joined)}")

    source = task.get("source_fragment")
    if source:
        lines.append(f"   💬 <i>«{escape(_trim_quote(str(source)))}»</i>")

    confidence = str(task.get("confidence") or "high")
    conf_label = CONFIDENCE_LABEL.get(confidence)
    if conf_label:
        lines.append(f"   {conf_label}")

    questions = task.get("clarification_questions") or []
    questions = [q for q in (str(q).strip() for q in questions) if q]
    if questions or task.get("needs_clarification"):
        lines.append("   <b>❓ Нужно уточнить:</b>")
        if questions:
            for q in questions:
                lines.append(f"      • {escape(q)}")
        else:
            lines.append("      • детали у жильца")

    return lines


def _format_unclear(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return []
    lines: list[str] = ["<b>❓ Непонятные фрагменты:</b>"]
    for item in items:
        fragment = escape(str(item.get("fragment") or "").strip())
        question = escape(str(item.get("question") or "").strip())
        reason = escape(str(item.get("reason") or "").strip())
        head = f"• «{fragment}»" if fragment else "•"
        if question:
            head += f" → {question}"
        elif reason:
            head += f" ({reason})"
        lines.append(head)
    return lines


def _trim_to_limit(lines: list[str], limit: int) -> str:
    """Join lines, never exceeding `limit` chars. Always break on newlines
    so we don't cut HTML tags in half (each line is fully-closed HTML).
    """
    out: list[str] = []
    size = 0
    truncated = False
    for line in lines:
        addition = (len(line) + 1) if out else len(line)  # +1 for "\n"
        if size + addition > limit:
            truncated = True
            break
        out.append(line)
        size += addition
    if truncated:
        out.append("…")
    return "\n".join(out)


def format_breakdown(data: dict[str, Any], *, max_chars: int = 3800) -> str:
    """Render a breakdown JSON as Telegram-safe HTML.

    Returns at most `max_chars` characters (Telegram's hard cap is 4096).
    Gracefully handles missing keys and unexpected shapes.
    """
    tasks = data.get("tasks") or []
    unclear = data.get("unclear_items") or []
    ignored = str(data.get("ignored_context") or "").strip()

    if not isinstance(tasks, list):
        tasks = []
    if not isinstance(unclear, list):
        unclear = []

    if not tasks and not unclear and not ignored:
        return "<i>Пустой разбор — задач не выделено.</i>"

    lines: list[str] = []
    if tasks:
        lines.append(f"<b>📋 Задач: {len(tasks)}</b>")
        lines.append("")
        for i, task in enumerate(tasks, 1):
            if not isinstance(task, dict):
                continue
            lines.extend(_format_task(i, task))
            lines.append("")  # blank line between tasks

    if unclear:
        lines.extend(_format_unclear(unclear))
        lines.append("")

    if ignored:
        lines.append("<b>ℹ️ Контекст без задач:</b>")
        lines.append(escape(ignored))

    # Drop trailing blank lines.
    while lines and not lines[-1]:
        lines.pop()

    return _trim_to_limit(lines, max_chars)
