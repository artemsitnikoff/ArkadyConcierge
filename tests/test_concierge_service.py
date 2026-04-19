import pytest

from app.services.concierge_service import (
    BreakdownAIError,
    BreakdownError,
    BreakdownParseError,
    BreakdownTimeoutError,
    ConciergeService,
)


class FakeAIClient:
    """Minimal drop-in for AIClient — returns a canned string or raises."""

    def __init__(self, *, reply: str | None = None, exc: BaseException | None = None):
        self._reply = reply
        self._exc = exc
        self.calls: list[str] = []

    async def complete(self, prompt: str, timeout: int = 180) -> str:
        self.calls.append(prompt)
        if self._exc is not None:
            raise self._exc
        assert self._reply is not None
        return self._reply

    async def close(self) -> None:
        return None


class TestConciergeService:
    async def test_happy_path_returns_parsed_json(self):
        ai = FakeAIClient(reply='{"tasks": [{"title": "x"}], "summary": "test"}')
        service = ConciergeService(ai)

        result = await service.breakdown("Сделай X и Y")

        assert result.data == {"tasks": [{"title": "x"}], "summary": "test"}
        assert len(ai.calls) == 1
        assert "Сделай X и Y" in ai.calls[0]

    async def test_fenced_json_is_parsed(self):
        ai = FakeAIClient(reply='```json\n{"ok": true}\n```')
        service = ConciergeService(ai)
        result = await service.breakdown("task")
        assert result.data == {"ok": True}

    async def test_empty_input_raises_breakdown_error(self):
        ai = FakeAIClient(reply="{}")
        service = ConciergeService(ai)
        with pytest.raises(BreakdownError, match="пустой текст"):
            await service.breakdown("   ")
        assert ai.calls == [], "AI should not be called for empty input"

    async def test_timeout_raises_breakdown_timeout_error(self):
        ai = FakeAIClient(exc=TimeoutError("claude CLI не ответил за 180с"))
        service = ConciergeService(ai)
        with pytest.raises(BreakdownTimeoutError):
            await service.breakdown("task")

    async def test_runtime_failure_raises_breakdown_ai_error(self):
        ai = FakeAIClient(exc=RuntimeError("claude CLI (code 1): boom"))
        service = ConciergeService(ai)
        with pytest.raises(BreakdownAIError):
            await service.breakdown("task")

    async def test_invalid_json_raises_breakdown_parse_error(self):
        ai = FakeAIClient(reply="this is definitely not json")
        service = ConciergeService(ai)
        with pytest.raises(BreakdownParseError):
            await service.breakdown("task")

    async def test_json_list_rejected(self):
        # Our pipeline expects a JSON object — bare lists must fail parse.
        ai = FakeAIClient(reply="[1, 2, 3]")
        service = ConciergeService(ai)
        with pytest.raises(BreakdownParseError):
            await service.breakdown("task")

    async def test_exception_hierarchy(self):
        # All specific errors must be catchable as the BreakdownError base.
        ai = FakeAIClient(exc=TimeoutError("x"))
        service = ConciergeService(ai)
        with pytest.raises(BreakdownError):
            await service.breakdown("task")
