"""HTTP API tests — isolated from the Telegram bot.

We build a tiny FastAPI app that mounts only `api_router` and installs a
fake ConciergeService in `app.state`. This avoids spinning up aiogram
polling (which needs a real bot token + network).
"""

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import TraceIdMiddleware
from app.api.routes import router as api_router
from app.services.concierge_service import BreakdownAIError


@dataclass
class FakeResult:
    data: dict


class FakeConciergeService:
    def __init__(self):
        self.calls: list[str] = []
        self.next_result: dict | BaseException = {"ok": True}

    async def breakdown(self, text: str):
        self.calls.append(text)
        if isinstance(self.next_result, BaseException):
            raise self.next_result
        return FakeResult(data=self.next_result)


@pytest.fixture
def api_app():
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    app.include_router(api_router, prefix="/api")
    app.state.concierge_service = FakeConciergeService()
    return app


@pytest.fixture
def client(api_app):
    return TestClient(api_app)


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body

    def test_health_sets_trace_id_header(self, client):
        r = client.get("/api/health")
        assert r.headers.get("x-trace-id", "").startswith("api-")

    def test_health_echoes_incoming_trace_id(self, client):
        r = client.get("/api/health", headers={"X-Trace-Id": "abc-123"})
        assert r.headers["x-trace-id"] == "abc-123"

    def test_rejects_oversize_trace_id(self, client):
        # 64 is the cutoff — 65 chars of `a` must be refused and replaced.
        r = client.get("/api/health", headers={"X-Trace-Id": "a" * 65})
        assert r.headers["x-trace-id"].startswith("api-")

    def test_rejects_trace_id_with_bad_chars(self, client):
        # Spaces, semicolons, CRLF-like payloads — all refused.
        for bad in ("foo bar", "a;b", "a\r\nInjected: yes", "a/b", "a.b"):
            r = client.get("/api/health", headers={"X-Trace-Id": bad})
            echoed = r.headers["x-trace-id"]
            assert echoed != bad, f"bad trace id {bad!r} was accepted"
            assert echoed.startswith("api-")

    def test_accepts_valid_id_like_trace_id(self, client):
        for ok in ("abc-123", "UPPER_and_lower", "tg-4242"):
            r = client.get("/api/health", headers={"X-Trace-Id": ok})
            assert r.headers["x-trace-id"] == ok


class TestBreakdownAuth:
    def test_missing_api_key_returns_401(self, client):
        r = client.post("/api/concierge/breakdown", json={"text": "do X"})
        assert r.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        r = client.post(
            "/api/concierge/breakdown",
            json={"text": "do X"},
            headers={"X-API-Key": "wrong"},
        )
        assert r.status_code == 401

    def test_correct_api_key_passes(self, client):
        r = client.post(
            "/api/concierge/breakdown",
            json={"text": "do X"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert r.status_code == 200


class TestBreakdownValidation:
    def test_empty_text_rejected(self, client):
        r = client.post(
            "/api/concierge/breakdown",
            json={"text": ""},
            headers={"X-API-Key": "test-api-key"},
        )
        assert r.status_code == 422  # pydantic min_length=1

    def test_missing_text_rejected(self, client):
        r = client.post(
            "/api/concierge/breakdown",
            json={},
            headers={"X-API-Key": "test-api-key"},
        )
        assert r.status_code == 422


class TestBreakdownHappy:
    def test_returns_service_data(self, api_app, client):
        service: FakeConciergeService = api_app.state.concierge_service
        service.next_result = {"tasks": [{"title": "call bob"}]}

        r = client.post(
            "/api/concierge/breakdown",
            json={"text": "task description"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert r.status_code == 200
        assert r.json() == {"data": {"tasks": [{"title": "call bob"}]}}
        assert service.calls == ["task description"]

    def test_service_error_returns_502(self, api_app, client):
        service: FakeConciergeService = api_app.state.concierge_service
        service.next_result = BreakdownAIError("claude failed")

        r = client.post(
            "/api/concierge/breakdown",
            json={"text": "task"},
            headers={"X-API-Key": "test-api-key"},
        )
        assert r.status_code == 502
        assert "claude failed" in r.json()["detail"]


class TestBreakdownWithDisabledAPIKey:
    def test_endpoint_returns_503_when_api_key_empty(self, monkeypatch, api_app):
        # Empty settings.api_key means "fail closed" — even a correct-looking
        # header should not let the request through.
        from app.config import settings
        from pydantic import SecretStr

        monkeypatch.setattr(settings, "api_key", SecretStr(""))

        client = TestClient(api_app)
        r = client.post(
            "/api/concierge/breakdown",
            json={"text": "task"},
            headers={"X-API-Key": "anything"},
        )
        assert r.status_code == 503
