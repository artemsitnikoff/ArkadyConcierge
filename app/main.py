import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import TraceIdMiddleware
from app.api.routes import router as api_router
from app.bot.create import create_bot, create_dispatcher
from app.config import settings
from app.logging_config import setup_logging
from app.services.ai_client import AIClient
from app.services.claude_token import init_token_file
from app.services.concierge_service import ConciergeService
from app.services.openrouter_client import OpenRouterClient
from app.version import __version__

setup_logging(level=settings.log_level, fmt=settings.log_format)
logger = logging.getLogger("concierge")

bot = create_bot()
dp = create_dispatcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_token_file()

    ai_client = AIClient()
    openrouter = OpenRouterClient()
    concierge_service = ConciergeService(ai_client)

    # `ai_client` is not injected into dispatcher — it's wrapped inside
    # `concierge_service` and never used directly by any handler.
    dp["openrouter"] = openrouter
    dp["concierge_service"] = concierge_service

    app.state.concierge_service = concierge_service

    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    logger.info("Bot polling started (v%s)", __version__)

    try:
        yield
    finally:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        await ai_client.close()
        await openrouter.close()
        logger.info("Shutdown complete")


app = FastAPI(
    title="ArkadyConcierge",
    description=(
        "Telegram concierge bot backend. Accepts free-form text or voice input, "
        "transcribes audio via OpenRouter (Gemini 2.5 Pro), and breaks tasks "
        "down into a structured JSON plan via Claude CLI (opus)."
    ),
    version=__version__,
    docs_url="/docs",
    lifespan=lifespan,
)

# TraceId middleware runs on every HTTP request — sets a ContextVar that
# the logging filter picks up so each request's log lines share a trace id.
app.add_middleware(TraceIdMiddleware)

app.include_router(api_router, prefix="/api")
