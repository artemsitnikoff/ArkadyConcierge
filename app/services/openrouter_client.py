"""OpenRouter client — voice transcription with speaker diarization.

Mirrors ArkadyJarvis pattern: Gemini 2.5 Pro with JSON response format, prompt
from prompts/voice_transcribe.md. Returns a structured TranscriptionResult.
"""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.config import settings
from app.services.prompts import load_prompt
from app.utils import parse_json_response

logger = logging.getLogger("concierge")

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class TranscriptionResult:
    success: bool
    error: str = ""
    speakers_count: int = 0
    segments: list[dict] = field(default_factory=list)
    full_text: str = ""


def _format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _explain_empty_content(finish_reason: str | None, refusal: str | None) -> str:
    if refusal:
        return f" (модель отказала: {refusal[:120]})"
    if finish_reason == "content_filter":
        return " (сработал контент-фильтр)"
    if finish_reason == "length":
        return " (ответ обрезан по лимиту токенов — запись слишком длинная)"
    if finish_reason == "stop":
        return " (модель завершила вывод с пустым ответом — возможно, речь не распознана)"
    return f" (finish_reason={finish_reason!r})"


def _read_and_encode(path: Path) -> str:
    """Read bytes and base64-encode them. Meant for `asyncio.to_thread`."""
    return base64.b64encode(path.read_bytes()).decode()


def _build_full_text(segments: list[dict]) -> str:
    parts = []
    for seg in segments:
        speaker = seg.get("speaker", "S?")
        start = float(seg.get("start", 0))
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        parts.append(f"{speaker} [{_format_time(start)}]: {text}")
    return "\n\n".join(parts)


class OpenRouterClient:
    """Async OpenRouter client — scoped to voice transcription."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.openrouter_timeout,
                write=settings.openrouter_timeout,
                pool=10.0,
            ),
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def transcribe_voice(self, audio_path: str | Path) -> TranscriptionResult:
        """Transcribe an OGG/OPUS voice file with speaker diarization."""
        path = Path(audio_path)
        try:
            # File read + b64 encode run in a worker thread to avoid blocking
            # the event loop on large voice messages (Telegram allows ~1 hour
            # voice notes up to ~20 MB, which is ~50 ms of blocking on SSD).
            audio_b64 = await asyncio.to_thread(_read_and_encode, path)
        except OSError as e:
            logger.error("Transcribe: cannot read %s: %s", path, e)
            return TranscriptionResult(success=False, error=f"не смог прочитать файл: {e}")

        prompt = load_prompt("voice_transcribe")
        payload = {
            "model": settings.openrouter_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "ogg"}},
                ],
            }],
            "response_format": {"type": "json_object"},
            # Gemini 2.5 Pro caps output at 65 536 tokens. 60k leaves headroom
            # for ~90 min of diarized speech. Lower values cause silent truncation.
            "max_tokens": 60000,
        }

        try:
            resp = await self._client.post(BASE_URL, json=payload)
        except httpx.HTTPError as e:
            logger.error("Transcribe HTTP error: %s", e, exc_info=True)
            return TranscriptionResult(success=False, error=str(e))

        if resp.status_code >= 400:
            body = resp.text[:300]
            logger.error("Transcribe %d: %s", resp.status_code, body)
            return TranscriptionResult(
                success=False, error=f"OpenRouter {resp.status_code}: {body}",
            )

        content: str | list | None = None
        finish_reason: str | None = None
        try:
            data = resp.json()
            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason", "?")
            message = choice.get("message") or {}
            content = message.get("content")
            refusal = message.get("refusal")
            if isinstance(content, list):
                content = "".join(p.get("text", "") for p in content if p.get("type") == "text")

            logger.info(
                "Transcribe finish_reason=%s content_len=%s usage=%s refusal=%r",
                finish_reason,
                len(content) if isinstance(content, str) else "n/a",
                data.get("usage"),
                refusal,
            )

            if not isinstance(content, str) or not content.strip():
                hint = _explain_empty_content(finish_reason, refusal)
                return TranscriptionResult(
                    success=False, error=f"модель не вернула текст{hint}",
                )

            parsed = parse_json_response(content)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            head = (content[:500] if isinstance(content, str) else str(content)[:500])
            tail = (content[-500:] if isinstance(content, str) and len(content) > 500 else "")
            logger.error(
                "Transcribe parse error: %s | finish_reason=%s | head=%r | tail=%r",
                e, finish_reason, head, tail, exc_info=True,
            )
            hint = " (ответ обрезан по лимиту токенов)" if finish_reason == "length" else ""
            return TranscriptionResult(
                success=False, error=f"не смог разобрать ответ: {e}{hint}",
            )

        segments = parsed.get("segments") or []
        for seg in segments:
            seg["start"] = max(0.0, float(seg.get("start", 0) or 0))
            seg["end"] = max(seg["start"], float(seg.get("end", seg["start"]) or seg["start"]))

        full_text = _build_full_text(segments)
        if not full_text:
            return TranscriptionResult(
                success=False,
                error="пустая расшифровка — возможно, тишина или слишком тихо",
            )

        return TranscriptionResult(
            success=True,
            speakers_count=int(parsed.get("speakers_count") or 0),
            segments=segments,
            full_text=full_text,
        )
