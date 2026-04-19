"""Test setup — must run BEFORE any `app.*` import.

Populates the env vars that pydantic Settings reads, so importing the app
module doesn't crash on missing BOT_TOKEN / API_KEY.
"""

import os

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("ALLOWED_USERS", "")
os.environ.setdefault("LOG_FORMAT", "plain")
