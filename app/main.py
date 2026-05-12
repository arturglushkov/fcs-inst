"""
MontazhBot — точка входа.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config.settings import settings
from app.core.cache.redis_client import redis_client
from app.core.database.engine import engine, Base
from app.bot.handlers.handlers import router as main_router
from app.bot.middlewares.middlewares import (
    AuthMiddleware, LoggingMiddleware, RateLimitMiddleware, ActiveUserMiddleware,
)
from app.models.models import (
    User, SiteObject, EmployeeObject, Shift, LocationLog,
    Task, Photo, Notification, WorkSchedule, AuditLog,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(main_router)
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(RateLimitMiddleware())
    dp.update.outer_middleware(AuthMiddleware())
    dp.message.outer_middleware(ActiveUserMiddleware())
    dp.callback_query.outer_middleware(ActiveUserMiddleware())
    return dp


async def create_db_tables() -> None:
    try:
        # Отдельные соединения для drop и create
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready ✅")
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise


async def main() -> None:
    bot = create_bot()
    dp  = create_dispatcher()

    logger.info("Starting MontazhBot...")

    await create_db_tables()

    try:
        await redis_client.connect()
        logger.info("Redis connected ✅")
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")

    try:
        from app.tasks.scheduler import setup_scheduler
        scheduler = setup_scheduler()
        scheduler.start()
        logger.info("Scheduler started ✅")
    except Exception as e:
        logger.warning(f"Scheduler failed: {e}")

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("MontazhBot polling started ✅")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await redis_client.disconnect()
        await engine.dispose()
        await bot.session.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
