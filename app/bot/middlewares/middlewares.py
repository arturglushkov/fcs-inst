"""
Middlewares для aiogram 3
"""

from __future__ import annotations
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.core.cache.redis_client import redis_client
from app.core.config.settings import settings

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Добавляет user_data в context для каждого апдейта."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        telegram_user = None
        if isinstance(event, Message):
            telegram_user = event.from_user
        elif isinstance(event, CallbackQuery):
            telegram_user = event.from_user

        if telegram_user:
            # Сначала Redis кэш
            cached = await redis_client.get_user_session(telegram_user.id)
            if cached:
                data["user_data"] = cached
            else:
                # Если нет в кэше — берём из БД
                try:
                    from app.core.database.engine import async_session_factory
                    from app.repositories.repositories import UserRepository
                    async with async_session_factory() as session:
                        repo = UserRepository(session)
                        user = await repo.get_by_telegram_id(telegram_user.id)
                        if user:
                            user_dict = {
                                "id": user.id,
                                "telegram_id": user.telegram_id,
                                "first_name": user.first_name,
                                "role": user.role if isinstance(user.role, str) else user.role.value,
                                "is_active": user.is_active,
                                "phone": user.phone,
                            }
                            await redis_client.set_user_session(
                                telegram_user.id, user_dict, expire=3600
                            )
                            data["user_data"] = user_dict
                        else:
                            data["user_data"] = None
                except Exception as e:
                    logger.error(f"AuthMiddleware DB error: {e}")
                    data["user_data"] = None

        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        start_time = time.monotonic()
        user_id = None
        action = "unknown"

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            action = f"message:{event.text[:30] if event.text else event.content_type}"
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            action = f"callback:{event.data}"

        try:
            result = await handler(event, data)
            elapsed = (time.monotonic() - start_time) * 1000
            logger.debug(f"[{user_id}] {action} → {elapsed:.0f}ms")
            return result
        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.error(f"[{user_id}] {action} → ERROR {elapsed:.0f}ms: {e}", exc_info=True)
            raise


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id if event.from_user else None

        if user_id:
            try:
                allowed = await redis_client.check_rate_limit(
                    user_id=user_id,
                    action="global",
                    limit=settings.RATE_LIMIT_REQUESTS,
                    window=settings.RATE_LIMIT_WINDOW_SECONDS,
                )
                if not allowed:
                    if isinstance(event, Message):
                        await event.answer("⚠️ Слишком много запросов. Подожди немного.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("⚠️ Слишком быстро!", show_alert=True)
                    return
            except Exception:
                pass  # Если Redis недоступен — пропускаем rate limit

        return await handler(event, data)


class ActiveUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_data = data.get("user_data")
        if user_data and user_data.get("is_active") is False:
            if isinstance(event, Message):
                await event.answer("🚫 Твой аккаунт заблокирован.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Аккаунт заблокирован.", show_alert=True)
            return
        return await handler(event, data)
