"""
Storage layer for preprocessing status.

Uses Redis as the sole storage backend, shared between the
FastAPI API process and Celery worker processes.`
"""
import json
from functools import lru_cache
from pathlib import Path

import redis
from loguru import logger

from app.models import PreprocessResponseModel

_REDIS_HASH_KEY = "preprocess:statuses"


class RedisStatusRepository:
    """
    Status repository backed by a single Redis Hash.
    """

    def __init__(self, redis_url: str):
        self._redis: redis.Redis[str] = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
        )
        # Verify connectivity
        self._redis.ping()
        count = self._redis.hlen(_REDIS_HASH_KEY)
        logger.info(f"Initialized RedisStatusRepository ({count} existing records) at {redis_url}")

    ##### Write #####

    def save(self, status: PreprocessResponseModel) -> None:
        """Save or update a preprocessing status in Redis."""
        self._redis.hset(
            _REDIS_HASH_KEY,
            key=status.request_id,
            value=status.model_dump_json(by_alias=True)
        )
        logger.info(f"Saved status for request {status.request_id}")

    ##### Read #####

    def get_by_id(self, request_id: str) -> PreprocessResponseModel | None:
        """Retrieve a single status by its request ID."""
        data = self._redis.hget(_REDIS_HASH_KEY, request_id)
        if not data:
            logger.warning(f"No status found for request {request_id}")
            return None
        return PreprocessResponseModel.model_validate_json(data)

    def get_all(self) -> list[PreprocessResponseModel]:
        """Retrieve all statuses, ordered by creation date (newest first)."""
        all_values = self._redis.hvals(_REDIS_HASH_KEY)
        if not all_values:
            logger.warning("No statuses found")
            return []
        statuses = [
            PreprocessResponseModel.model_validate_json(v)
            for v in all_values
        ]
        return sorted(statuses, key=lambda s: s.created_at, reverse=True)

    ##### Utils #####

    def export_to_json(self, output_path: Path, request_id: str | None = None) -> None:
        """Export all or one status to a JSON file (for backups / automation)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if request_id:
            status = self.get_by_id(request_id)
            data = [status.model_dump(by_alias=True, mode="json")] if status else []
        else:
            statuses = self.get_all()
            data = [s.model_dump(by_alias=True, mode="json") for s in statuses]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"Exported {len(data)} statuses to {output_path}")

    def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            return self._redis.ping()
        except redis.ConnectionError:
            return False

    def close(self) -> None:
        """Close the Redis connection."""
        self._redis.close()
        logger.info("Redis connection closed")


@lru_cache(maxsize=1)
def get_redis_repository(redis_url: str) -> RedisStatusRepository:
    """
    Cached version of Redis status repository.
    """
    return RedisStatusRepository(redis_url=redis_url)