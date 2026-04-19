import io
import json
import logging

import pytest

from app.logging_config import (
    get_trace_id,
    new_trace_id,
    reset_trace_id,
    set_trace_id,
    setup_logging,
)


@pytest.fixture
def captured_stream():
    """Replace the root logger's handler with one that writes to an in-memory
    stream, so we can assert on the final formatted output. Restores the
    original root logger state on teardown — `setup_logging` mutates it
    globally and would leak DEBUG level + swapped handlers into other tests.
    """
    stream = io.StringIO()
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    def _setup(fmt: str):
        setup_logging(level="DEBUG", fmt=fmt)
        assert root.handlers, "setup_logging must install at least one handler"
        root.handlers[0].stream = stream
        return stream

    try:
        yield _setup
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)


class TestTraceIdContextVar:
    def test_default_is_dash(self):
        # Fresh context — no trace id bound.
        assert get_trace_id() == "-"

    def test_set_and_reset(self):
        token = set_trace_id("abc")
        assert get_trace_id() == "abc"
        reset_trace_id(token)
        assert get_trace_id() == "-"

    def test_new_trace_id_has_prefix(self):
        tid = new_trace_id(prefix="api-")
        assert tid.startswith("api-")
        assert len(tid) > len("api-")

    def test_new_trace_id_is_unique(self):
        ids = {new_trace_id() for _ in range(10)}
        assert len(ids) == 10


class TestPlainFormat:
    def test_trace_id_appears_in_output(self, captured_stream):
        stream = captured_stream("plain")
        token = set_trace_id("trace-xyz")
        try:
            logging.getLogger("concierge").info("hello")
        finally:
            reset_trace_id(token)

        output = stream.getvalue()
        assert "trace-xyz" in output
        assert "hello" in output

    def test_default_trace_id_is_dash(self, captured_stream):
        stream = captured_stream("plain")
        logging.getLogger("concierge").info("msg")
        assert "[-]" in stream.getvalue()


class TestJsonFormat:
    def test_emits_valid_json_per_line(self, captured_stream):
        stream = captured_stream("json")
        token = set_trace_id("trace-json")
        try:
            logging.getLogger("concierge").info("structured msg")
        finally:
            reset_trace_id(token)

        line = stream.getvalue().strip()
        payload = json.loads(line)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "concierge"
        assert payload["msg"] == "structured msg"
        assert payload["trace_id"] == "trace-json"
        assert "ts" in payload

    def test_extra_fields_are_included(self, captured_stream):
        stream = captured_stream("json")
        logging.getLogger("concierge").info(
            "with extras",
            extra={"user_id": 42, "action": "ping"},
        )
        payload = json.loads(stream.getvalue().strip())
        assert payload["user_id"] == 42
        assert payload["action"] == "ping"

    def test_exception_is_serialized(self, captured_stream):
        stream = captured_stream("json")
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logging.getLogger("concierge").error("caught", exc_info=True)

        payload = json.loads(stream.getvalue().strip())
        assert "RuntimeError" in payload["exc"]
        assert "boom" in payload["exc"]
