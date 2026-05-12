from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ────────────────────────────────────────
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_LOG_LEVEL: str = "INFO"
    APP_TIMEZONE: str = "Europe/Kiev"

    # ── Bot ───────────────────────────────────────
    BOT_TOKEN: str
    BOT_WEBHOOK_URL: str = ""
    BOT_WEBHOOK_SECRET: str = ""

    # ── Database ──────────────────────────────────
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # ── Redis ─────────────────────────────────────
    REDIS_URL: str

    # ── JWT ───────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Admin API ─────────────────────────────────
    API_SECRET_KEY: str
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    # ── S3 Storage ────────────────────────────────
    S3_ENDPOINT_URL: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET_NAME: str = "montazh-photos"
    S3_PUBLIC_URL: str = ""

    # ── AI ────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # ── Geo ───────────────────────────────────────
    GEO_CHECK_RADIUS_METERS: int = 100
    GEO_TRACKING_INTERVAL_MINUTES: int = 15

    # ── Notifications ─────────────────────────────
    NOTIFY_LATE_MINUTES: int = 15
    NOTIFY_OVERTIME_HOURS: int = 9

    # ── Rate Limiting ─────────────────────────────
    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Encryption ────────────────────────────────
    ENCRYPTION_KEY: str

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def use_webhook(self) -> bool:
        return bool(self.BOT_WEBHOOK_URL)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
