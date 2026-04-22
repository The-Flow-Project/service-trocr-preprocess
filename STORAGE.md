# Storage System Documentation

## Overview

The service uses **Redis** as its sole storage backend for persisting preprocessing status. Redis is shared between the FastAPI API process and Celery worker processes via a single `REDIS_URL`.

## Why Redis?

- Shared between FastAPI and Celery worker processes (separate processes)
- Sub-millisecond reads/writes
- Automatic persistence (RDB/AOF)
- Already required as Celery message broker — no additional infrastructure
- Thread-safe by design (single-threaded event loop)
- Optional JSON backup export via `export_to_json()`

---

## Architecture

```
┌─────────────────────┐          ┌─────────────────────┐
│   FastAPI Service    │          │   Celery Worker      │
│     (main.py)        │          │    (tasks.py)        │
└──────────┬──────────┘          └──────────┬──────────┘
           │  Depends(get_repository)        │  _get_repository()
           ▼                                 ▼
┌─────────────────────────────────────────────────────┐
│             RedisStatusRepository                    │
│  Hash key: preprocess:statuses                       │
│  Fields:   {request_id} → JSON PreprocessResponse    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │   Redis 7+     │
              │  (redis:6379)  │
              └────────────────┘
```

---

## Configuration

### Environment Variables

```bash
# .env

# API Key (required)
API_KEY=your_secret_api_key

# Redis URL — used as Celery broker AND status storage
REDIS_URL=redis://localhost:6379/0

# Log level
LOG_LEVEL=INFO
```

---

## Redis Hash Schema

All preprocessing statuses are stored as fields in a **single Redis Hash**:

```
Hash key:  preprocess:statuses
Field:     {request_id}
Value:     JSON-serialized PreprocessResponseModel
```

This uses `HSET` / `HGET` / `HVALS` instead of individual string keys, which:
- Avoids the expensive `KEYS` pattern scan
- Retrieves all statuses in a single `HVALS` roundtrip
- Cleanly isolates status data from Celery broker keys

Example field value:

```json
{
  "request_id": "123e4567-e89b-12d3-a456-426614174000",
  "source": "https://example.com/data.zip",
  "state": "completed",
  "created_at": "2026-03-12T10:30:00",
  "runtime": 42.5,
  "total_pages": 120,
  "total_regions": 480,
  "total_lines": 2400,
  "average_regions_per_page": 4.0,
  "average_lines_per_page": 20.0
}
```

---

## Lifecycle

1. **Startup**: `RedisStatusRepository` connects to Redis, verifies with `PING`, counts existing records via `HLEN`.
2. **Runtime**: `save()` → `HSET`; `get_by_id()` → `HGET`; `get_all()` → `HVALS` + sort by `created_at`.
3. **Shutdown**: Connection close via `close()`.

---

## Thread Safety

Redis operations are atomic. The synchronous `redis-py` client handles connection pooling internally. No additional locking required.

---

## Limitations

- Requires a running Redis instance (added via `docker-compose.yml`).
- `get_all()` uses `HVALS` — O(n) for n statuses, but all within one Hash (no full DB scan). Fine for < 100,000 jobs.
- No per-field TTL possible on a Redis Hash. If automatic expiry is needed later, switch to individual keys with `EXPIRE`.
