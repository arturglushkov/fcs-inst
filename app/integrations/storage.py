"""S3 / MinIO storage для фотоотчётов."""

from __future__ import annotations
import logging
from typing import Tuple, Optional
import aioboto3
from app.core.config.settings import settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self) -> None:
        self._session = aioboto3.Session()

    def _get_client(self):
        return self._session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
        )

    async def upload_photo(
        self,
        data: bytes,
        key: str,
        content_type: str = "image/jpeg",
    ) -> Tuple[str, Optional[str]]:
        """Загружает файл и возвращает (s3_key, public_url)."""
        try:
            async with self._get_client() as client:
                await client.put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
            url = f"{settings.S3_PUBLIC_URL}/{settings.S3_BUCKET_NAME}/{key}" if settings.S3_PUBLIC_URL else None
            return key, url
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            return key, None

    async def get_presigned_url(self, key: str, expires: int = 3600) -> Optional[str]:
        try:
            async with self._get_client() as client:
                url = await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
                    ExpiresIn=expires,
                )
            return url
        except Exception as e:
            logger.error(f"Presigned URL failed: {e}")
            return None

    async def ensure_bucket_exists(self) -> None:
        try:
            async with self._get_client() as client:
                try:
                    await client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
                except Exception:
                    await client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
                    logger.info(f"Created bucket: {settings.S3_BUCKET_NAME}")
        except Exception as e:
            logger.error(f"Bucket setup failed: {e}")


storage_service = StorageService()
