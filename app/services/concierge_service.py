"""Concierge service — text → structured JSON breakdown.

The breakdown prompt lives in prompts/concierge_breakdown.md and is owned by
the user (editable without touching code). This service loads the prompt,
calls the Claude CLI, and parses the JSON reply into a plain dict.
"""

import logging
from dataclasses import dataclass

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
    data: dict
    raw: str


class ConciergeService:
    """Breaks down a free-form task description into a structured JSON plan."""

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client

    async def breakdown(self, text: str) -> BreakdownResult:
        text = (text or "").strip()
        if not text:
            raise BreakdownError("пустой текст — нечего разбирать")

        template = load_prompt(BREAKDOWN_PROMPT_NAME)
        prompt = template.replace("{text}", text) if "{text}" in template else f"{template}\n\n{text}"

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
