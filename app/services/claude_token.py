"""Claude OAuth token auto-refresh.

Mirrors ArkadyJarvis pattern: tokens are stored in data/.claude_token.json,
refresh tokens are single-use, endpoint is Anthropic's OAuth token service.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("concierge")

TOKEN_FILE = Path("data/.claude_token.json")
TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
REFRESH_BUFFER_MS = 600_000  # refresh 10 min before expiry

_refresh_lock = asyncio.Lock()

# In-memory cache of the token file. Reads are cheap (<1 ms) but happen on
# every Claude CLI call — keeping state in process saves the syscall and
# avoids racing with external token rotation (we own the file).
_cache: dict[str, Any] = {}


def _load() -> dict[str, Any]:
    if _cache:
        return _cache
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            if isinstance(data, dict):
                _cache.update(data)
                return _cache
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s", TOKEN_FILE, e)
    return {}


def _save(data: dict[str, Any]) -> None:
    # Atomic write: refresh tokens are single-use, so a torn write would
    # brick auth. Write to a tmp file in the same directory, then rename.
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(TOKEN_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(TOKEN_FILE)
    _cache.clear()
    _cache.update(data)


def init_token_file() -> None:
    """Seed the token file from Settings on first run.

    Reads via the pydantic Settings object rather than `os.environ` directly,
    so `.env`-only values (not exported to the process env) also work.
    """
    if TOKEN_FILE.exists():
        data = _load()
        if data.get("refresh_token"):
            logger.info("Claude token file exists with refresh token")
            return

    access_token = settings.claude_code_oauth_token
    refresh_token = settings.claude_refresh_token

    if not refresh_token:
        if access_token:
            logger.warning(
                "CLAUDE_CODE_OAUTH_TOKEN set but no CLAUDE_REFRESH_TOKEN — "
                "token will not auto-refresh"
            )
        return

    data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": 0,
    }
    _save(data)
    logger.info("Claude token file initialized from settings")


async def ensure_fresh_token() -> None:
    """Refresh the Claude OAuth access token if close to expiry."""
    async with _refresh_lock:
        data = _load()
        now_ms = time.time() * 1000

        if data.get("expires_at", 0) > now_ms + REFRESH_BUFFER_MS:
            if data.get("access_token"):
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = data["access_token"]
            return

        refresh_token = data.get("refresh_token")
        if not refresh_token:
            logger.debug("No refresh token available, using current access token")
            return

        logger.info("Refreshing Claude OAuth token...")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": settings.claude_oauth_client_id,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                result = resp.json()

            new_access = result["access_token"]
            new_refresh = result["refresh_token"]
            expires_in = result.get("expires_in", 28800)

            new_data = {
                "access_token": new_access,
                "refresh_token": new_refresh,
                "expires_at": now_ms + expires_in * 1000,
            }
            _save(new_data)
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = new_access
            logger.info("Claude token refreshed, expires in %d hours", expires_in // 3600)

        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.error("Failed to refresh Claude token: %s", e, exc_info=True)
            if data.get("access_token"):
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = data["access_token"]
