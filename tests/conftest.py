import os
import sys
from pathlib import Path

# Settings() is evaluated at import time of app.main, so configure env first.
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class FakeRepository:
    """In-memory stand-in for RedisStatusRepository."""

    def __init__(self):
        self.items = {}

    def save(self, status):
        self.items[status.request_id] = status

    def get_by_id(self, request_id):
        return self.items.get(request_id)

    def get_all(self):
        return list(self.items.values())

    def ping(self):
        return True

    def close(self):
        pass


FAKE_REPOSITORY = FakeRepository()

# app.celery_app connects to Redis at import time, so the factory must be
# replaced before app.main (and thus app.celery_app) is first imported.
import app.storage as _storage  # noqa: E402

_storage.get_redis_repository = lambda redis_url=None: FAKE_REPOSITORY
