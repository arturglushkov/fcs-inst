import json
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config.settings import settings


class RedisClient:
    def __init__(self) -> None:
        self._client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> aioredis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected")
        return self._client

    # ── Generic ────────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[str]:
        return await self.client.get(key)

    async def set(self, key: str, value: str, expire: int = 0) -> None:
        if expire:
            await self.client.setex(key, expire, value)
        else:
            await self.client.set(key, value)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(key))

    # ── JSON helpers ───────────────────────────────────────────────

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, expire: int = 0) -> None:
        await self.set(key, json.dumps(value, default=str), expire)

    # ── Session / Auth ─────────────────────────────────────────────

    async def set_user_session(self, user_id: int, data: dict, expire: int = 3600) -> None:
        await self.set_json(f"session:{user_id}", data, expire)

    async def get_user_session(self, user_id: int) -> Optional[dict]:
        return await self.get_json(f"session:{user_id}")

    async def delete_user_session(self, user_id: int) -> None:
        await self.delete(f"session:{user_id}")

    # ── Rate limiting ──────────────────────────────────────────────

    async def check_rate_limit(self, user_id: int, action: str, limit: int, window: int) -> bool:
        """Returns True если лимит НЕ превышен."""
        key = f"rl:{action}:{user_id}"
        pipe = self.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        count = results[0]
        return count <= limit

    # ── Geo tracking cache ─────────────────────────────────────────

    async def update_employee_location(self, employee_id: int, lat: float, lon: float) -> None:
        data = {"lat": lat, "lon": lon}
        await self.set_json(f"location:{employee_id}", data, expire=3600)

    async def get_employee_location(self, employee_id: int) -> Optional[dict]:
        return await self.get_json(f"location:{employee_id}")

    async def get_all_active_locations(self) -> dict[int, dict]:
        """Возвращает location всех активных сотрудников."""
        keys = await self.client.keys("location:*")
        result = {}
        for key in keys:
            emp_id = int(key.split(":")[1])
            data = await self.get_json(key)
            if data:
                result[emp_id] = data
        return result

    # ── State machine (FSM альтернатива) ───────────────────────────

    async def set_user_state(self, user_id: int, state: str, data: dict | None = None) -> None:
        payload = {"state": state, "data": data or {}}
        await self.set_json(f"state:{user_id}", payload, expire=1800)

    async def get_user_state(self, user_id: int) -> Optional[dict]:
        return await self.get_json(f"state:{user_id}")

    async def clear_user_state(self, user_id: int) -> None:
        await self.delete(f"state:{user_id}")


redis_client = RedisClient()
