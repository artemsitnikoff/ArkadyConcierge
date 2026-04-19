"""Concierge service — text → structured JSON breakdown.

The breakdown prompt lives in prompts/concierge_breakdown.md and is owned by
the user (editable without touching code). This service loads the prompt,
fills in meta-context placeholders, calls the Claude CLI, and parses the
JSON reply into a plain dict.

Supported placeholders in the prompt template:
  • `{{current_datetime}}` — ISO 8601 with local timezone offset
  • `{{resident_name}}`    — resident display name, or empty
  • `{{apartment}}`        — apartment number, or empty
  • `{text}`               — resident message (if absent, the text is
                             appended to the prompt under a header)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.ai_client import AIClient
from app.services.prompts import load_prompt
from app.utils import parse_json_response

logger = logging.getLogger("concierge")

BREAKDOWN_PROMPT_NAME = "concierge_breakdown"
BREAKDOWN_TIMEOUT_SEC = 240


class BreakdownError(RuntimeError):
    """Base class for any failure in the concierge breakdown pipeline."""


class BreakdownTimeoutError(BreakdownError):
    """Claude CLI did not respond within the configured timeout."""


class BreakdownAIError(BreakdownError):
    """Claude CLI failed for non-timeout reasons (non-zero exit, empty output)."""


class BreakdownParseError(BreakdownError):
    """Claude CLI responded but the output was not valid JSON."""


@dataclass
class BreakdownResult:
    data: dict[str, Any]
    raw: str


def _now_iso() -> str:
    """Current time in ISO 8601 with local timezone offset, second precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _build_prompt(
    template: str,
    text: str,
    *,
    resident_name: str = "",
    apartment: str = "",
) -> str:
    """Substitute `{{...}}` meta placeholders and attach the resident message."""
    prompt = (
        template
        .replace("{{current_datetime}}", _now_iso())
        .replace("{{resident_name}}", resident_name)
        .replace("{{apartment}}", apartment)
    )
    if "{text}" in prompt:
        return prompt.replace("{text}", text)
    return f"{prompt}\n\n---\nВХОДНОЕ СООБЩЕНИЕ ОТ ЖИЛЬЦА:\n{text}"


class ConciergeService:
    """Breaks down a free-form task description into a structured JSON plan."""

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client

    async def breakdown(
        self,
        text: str,
        *,
        resident_name: str = "",
        apartment: str = "",
    ) -> BreakdownResult:
        text = (text or "").strip()
        if not text:
            raise BreakdownError("пустой текст — нечего разбирать")

        template = load_prompt(BREAKDOWN_PROMPT_NAME)
        prompt = _build_prompt(
            template, text,
            resident_name=resident_name,
            apartment=apartment,
        )

        try:
            raw = await self._ai.complete(prompt, timeout=BREAKDOWN_TIMEOUT_SEC)
        except TimeoutError as e:
            raise BreakdownTimeoutError(str(e)) from e
        except RuntimeError as e:
            raise BreakdownAIError(str(e)) from e

        try:
            data = parse_json_response(raw)
        except (ValueError, TypeError) as e:
            logger.error("Breakdown parse error: %s | raw head=%r", e, raw[:400])
            raise BreakdownParseError(f"не смог разобрать JSON: {e}") from e

        return BreakdownResult(data=data, raw=raw)
