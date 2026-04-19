"""Concierge router — the bot's single feature.

Inputs (outside /start and /help handled by start.py):
  • Telegram voice note (F.voice) → transcribe → breakdown
  • Plain text (F.text)           → breakdown
"""

import html
import json
import logging
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message

from app.config import settings
from app.services.concierge_service import (
    BreakdownAIError,
    BreakdownError,
    BreakdownParseError,
    BreakdownTimeoutError,
    ConciergeService,
)
from app.services.openrouter_client import OpenRouterClient

logger = logging.getLogger("concierge")
router = Router()

# Telegram hard cap is 4096 chars/message. We reserve ~200 chars for
# surrounding text ("✅ Расшифровка...", "\n\n🧩 Разбираю..."), headers
# and HTML tags, and cap escaped body at this threshold.
_TELEGRAM_SAFE_LIMIT = 3800


def _escape_preview(text: str) -> str:
    """HTML-escape `text` and guarantee the result fits a Telegram message.

    Character-slicing before escape isn't enough: `<` becomes `&lt;` (×4),
    so heavily-punctuated JSON can balloon past the 4096-char limit.
    Slicing *after* escape is also dangerous — we can cut mid-entity
    (e.g. `&am` instead of `&amp;`) and Telegram will refuse to parse.

    Strategy: escape, then if too long, truncate and walk back to the
    last character that is not inside an unfinished entity.
    """
    escaped = html.escape(text[:_TELEGRAM_SAFE_LIMIT])
    if len(escaped) <= _TELEGRAM_SAFE_LIMIT:
        return escaped

    cut = escaped[:_TELEGRAM_SAFE_LIMIT - 1]
    # If the tail contains `&` without a closing `;`, we've cut mid-entity.
    # Drop back to just before that `&`. The longest HTML entity we emit is
    # `&quot;` (6 chars), so scanning the last 8 chars is enough.
    tail_start = max(0, len(cut) - 8)
    amp = cut.rfind("&", tail_start)
    if amp != -1 and cut.find(";", amp) == -1:
        cut = cut[:amp]
    return cut + "…"


@router.message(F.voice)
async def handle_voice(
    message: Message,
    bot: Bot,
    concierge_service: ConciergeService,
    openrouter: OpenRouterClient,
) -> None:
    duration = message.voice.duration or 0
    logger.info(
        "concierge voice: duration=%ss user=%s",
        duration, message.from_user.id if message.from_user else "?",
    )
    if duration > settings.max_voice_duration_sec:
        await message.reply(
            f"❌ Голосовое слишком длинное: {duration} сек. "
            f"Лимит — {settings.max_voice_duration_sec} сек. "
            "Разбей на куски или пришли текстом."
        )
        return

    wait = await message.reply("🎤 Расшифровываю голосовое...")

    ogg_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            ogg_path = Path(tmp.name)
        await bot.download(message.voice, destination=ogg_path)
        result = await openrouter.transcribe_voice(ogg_path)
    finally:
        if ogg_path is not None:
            try:
                ogg_path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Failed to delete temp ogg %s: %s", ogg_path, e)

    if not result.success:
        await wait.edit_text(
            f"❌ Не смог расшифровать голосовое: {result.error}\n\n"
            "Попробуй ещё раз или напиши текстом."
        )
        return

    await wait.edit_text(
        f"✅ Расшифровка (спикеров: {result.speakers_count}):\n\n"
        f"<code>{_escape_preview(result.full_text)}</code>\n\n"
        "🧩 Разбираю задачу...",
    )
    await _run_breakdown(message, result.full_text, service=concierge_service)


@router.message(F.text)
async def handle_text(
    message: Message, concierge_service: ConciergeService,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        # Unknown command — /start and /help are handled by start.py first.
        await message.reply(
            "Не знаю такую команду. Пришли задачу текстом или голосовым, или /help."
        )
        return
    wait = await message.reply("🧩 Разбираю задачу...")
    await _run_breakdown(message, text, service=concierge_service, wait=wait)


async def _run_breakdown(
    message: Message,
    text: str,
    *,
    service: ConciergeService,
    wait: Message | None = None,
) -> None:
    try:
        result = await service.breakdown(text)
    except BreakdownTimeoutError as e:
        reply = f"⏱ AI не успел ответить: {e}\n\nПопробуй разбить задачу на части покороче."
        await _reply_or_edit(reply, message=message, wait=wait)
        return
    except BreakdownParseError as e:
        reply = f"🤖 AI вернул невалидный JSON: {e}\n\nПопробуй переформулировать."
        await _reply_or_edit(reply, message=message, wait=wait)
        return
    except BreakdownAIError as e:
        reply = f"❌ AI-ошибка: {e}"
        await _reply_or_edit(reply, message=message, wait=wait)
        return
    except BreakdownError as e:
        # Catch-all for future subclasses / direct BreakdownError raises.
        await _reply_or_edit(f"❌ {e}", message=message, wait=wait)
        return

    pretty = json.dumps(result.data, ensure_ascii=False, indent=2)

    await message.answer_document(
        BufferedInputFile(pretty.encode("utf-8"), filename="breakdown.json"),
        caption="📦 JSON-разбор задачи",
    )
    await message.answer(f"<pre>{_escape_preview(pretty)}</pre>")

    if wait:
        try:
            await wait.delete()
        except TelegramAPIError as e:
            logger.debug("Could not delete wait message: %s", e)


async def _reply_or_edit(text: str, *, message: Message, wait: Message | None) -> None:
    """Send `text` via wait.edit_text if we have a wait message, else reply."""
    try:
        if wait:
            await wait.edit_text(text)
        else:
            await message.reply(text)
    except TelegramAPIError as e:
        logger.warning("Could not deliver error reply: %s", e)
