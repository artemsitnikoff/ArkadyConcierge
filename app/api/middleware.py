"""ASGI middleware — per-request trace_id propagation.

Reads `X-Trace-Id` from the incoming request (for cross-service correlation),
or generates a fresh one. Binds it to a ContextVar so downstream logger
calls get it automatically, and echoes it back in `X-Trace-Id` response
header.

Incoming trace ids are validated before trust — we refuse to log or echo
client-controlled strings that could contain header-injection payloads,
control characters, or arbitrary-length blobs.
"""

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import new_trace_id, reset_trace_id, set_trace_id

logger = logging.getLogger("concierge.api")

_MAX_TRACE_ID = 64
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _accept_incoming(value: str | None) -> str | None:
    """Return the header value only if it's a safe, short, id-like string."""
    if not value:
        return None
    if len(value) > _MAX_TRACE_ID:
        return None
    if not _TRACE_ID_RE.match(value):
        return None
    return value


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = _accept_incoming(request.headers.get("x-trace-id"))
        trace_id = incoming or new_trace_id(prefix="api-")

        token = set_trace_id(trace_id)
        try:
            response = await call_next(request)
        finally:
            reset_trace_id(token)

        response.headers["X-Trace-Id"] = trace_id
        return response
