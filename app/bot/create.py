from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.middlewares import AccessMiddleware, ErrorMiddleware, TraceIdMiddleware
from app.config import settings


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # Middleware chain: TraceId → Error → Access → handler.
    # TraceId must be outermost so every log line emitted by Error/Access
    # inherits the same trace id. Must be registered before include_routers
    # in aiogram 3.x — later registrations on an already-attached router
    # can be silently dropped.
    dp.message.outer_middleware(TraceIdMiddleware())
    dp.callback_query.outer_middleware(TraceIdMiddleware())
    dp.message.outer_middleware(ErrorMiddleware())
    dp.callback_query.outer_middleware(ErrorMiddleware())
    dp.message.outer_middleware(AccessMiddleware())
    dp.callback_query.outer_middleware(AccessMiddleware())

    from app.bot.routers.start import router as start_router
    from app.bot.routers.concierge import router as concierge_router

    dp.include_routers(
        start_router,
        concierge_router,
    )
    return dp
