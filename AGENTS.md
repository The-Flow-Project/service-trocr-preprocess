# Service TrOCR Preprocess - Agent Guidelines

This document provides essential context for AI agents working on the `service-trocr-preprocess` codebase, a FastAPI microservice for preparing TrOCR training data.

## 🏗 System Architecture

### Core Components
- **Entry Point**: `src/app/main.py` initializes the FastAPI app, middleware (CORS, RateLimit, HTTPS redirect in production), and dependency injection.
- **Celery Tasks**: `src/app/tasks.py` defines Celery tasks for background preprocessing. Tasks receive only JSON-serializable arguments and reconstruct Pydantic models internally.
- **Celery App**: `src/app/celery_app.py` configures the Celery instance (Redis broker, serialization, robustness settings).
- **Worker Helpers**: `src/app/worker.py` contains shared helper functions (e.g. `upload_status_to_huggingface`) used by Celery tasks.
- **Storage Layer**: `src/app/storage.py` provides a Redis-backed storage backend:
  - **`RedisStatusRepository`** — stores all statuses as fields in a single Redis Hash (`preprocess:statuses`). Uses `HSET`/`HGET`/`HVALS` instead of individual string keys.
  - **Factory**: `create_repository(redis_url)` creates the instance.
  - **Pattern**: Business logic accesses the repository via FastAPI dependency injection (`Depends(get_repository)`), which retrieves the singleton from `app.state`.
- **Models**: `src/app/models.py` defines Pydantic v2 models for API requests/responses and internal configuration (`Settings` via `pydantic-settings`).
  - **Inheritance**: `PreprocessBaseModel` extends `PreprocessorBaseConfig` from the `flow-preprocessing` package. When modifying request/response fields, check whether the field belongs here or in the upstream base config.
  - **Settings**: Includes `REDIS_URL`, `API_KEY`, `ENVIRONMENT`, `LOG_LEVEL`, and CORS settings. All loaded from `.env` / environment variables.
- **Version**: `src/app/__init__.py` defines `__version__` (currently `0.9.0`), exposed via the `/health` endpoint.

### Data Flow
1. **API Request**: Authenticated via `X-API-KEY` header (timing-safe comparison with `secrets.compare_digest`).
2. **Task Creation**: Service creates a `PreprocessResponseModel` status record (`state: in_progress`), saves it to the shared storage (Redis), and returns it with a `request_id` immediately (HTTP 201).
3. **Celery Task Dispatch**: `preprocess_task.delay()` sends the job to Redis as a Celery message. The FastAPI process does **not** wait for completion.
4. **Background Processing** (Celery Worker):
   - `tasks.preprocess_task` runs in a separate Celery worker process.
   - Reconstructs `PreprocessResponseModel` from the JSON dict argument.
   - Creates its own `RedisStatusRepository` connection (cannot access `app.state`).
   - Delegates image/XML processing to `flow-preprocessing` (`ZipPreprocessor` or `HuggingFacePreprocessor`).
   - On success: updates state to `completed`, collects statistics, saves to Redis.
   - On failure: updates state to `failed`, saves to Redis.
   - Optionally uploads final status JSON to a Hugging Face dataset repository.

### API Endpoints
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/preprocess/zip` | ✅ | Start preprocessing from a ZIP URL |
| `POST` | `/preprocess/hf` | ✅ | Start preprocessing from a HuggingFace repo |
| `GET` | `/status` | ✅ | List all preprocessing statuses |
| `GET` | `/status/{uuid}` | ✅ | Get a single status by request ID |
| `GET` | `/health` | ❌ | Health check (no API key required) |

## 🛠 Developer Workflows & Commands

### Dependency Management
The project uses `uv` for fast package management.
- **Install**: `uv sync` (creates venv and installs deps).
- **Add Dependency**: `uv add <package>`.
- **Export Requirements**: `uv pip compile pyproject.toml -o requirements.txt` (for Docker compatibility if not using uv in container).

### Running Locally
1. **Start Redis**: `docker compose up redis -d` (or install Redis locally).
2. **Dev Server**: `uv run uvicorn src.app.main:app --reload`
3. **Celery Worker** (separate terminal): `cd src && uv run celery -A app.tasks worker --loglevel=debug`
4. **Environment**: Ensure `.env` exists (copy from `.env.example`). Key variables:
   - `API_KEY`: Required for all authenticated endpoints.
   - `REDIS_URL`: Redis connection URL (default `redis://localhost:6379/0`). Used as Celery broker and status storage.
   - `ENVIRONMENT`: `development` (default) or `production`. Controls HTTPS redirect and docs visibility.
   - `LOG_LEVEL`: One of `TRACE`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`).
   - `CORS_ALLOWED_ORIGINS`, `CORS_ALLOWED_HEADERS`, `CORS_ALLOWED_METHODS`: JSON-encoded lists for CORS middleware (see `.env.example`).

### Docker
```bash
docker compose up --build        # Start all services (Redis, API, Celery Worker)
docker compose up redis -d       # Start only Redis for local development
docker compose logs celery-worker -f  # Follow worker logs
```

### Testing
- No explicit `tests/` folder. Manual API testing via `/docs` (Swagger UI, development only) or `curl`.

## 🧩 Codebase Conventions

### Celery Task Arguments
- Celery tasks **must only receive JSON-serializable arguments** (str, int, float, dict, list, None).
- **Never** pass Pydantic models or repository instances as task arguments.
- Tasks reconstruct `PreprocessResponseModel` via `model_validate(status_dict)` and create their own repository connection internally.

### Async Endpoints
- All API route handlers are `async def` (FastAPI standard).
- `preprocess_task.delay()` is non-blocking — it just sends a message to Redis.
- `RedisStatusRepository` uses the synchronous `redis-py` client. Redis reads are <1ms, so calling them from `async def` handlers is acceptable.

### Logging
- **Library**: `loguru` (not stdlib `logging`).
- **Pattern**: `from loguru import logger`.
- **Configuration**: Managed in `src/app/logging_config.py`. Initialized both in `main.py` (API process) and `celery_app.py` (worker process).
  - `logs/app.log`: All logs (≥ DEBUG), rotated at 5 MB, 10 days retention.
  - `logs/errors.log`: Errors only (≥ ERROR), rotated at 5 MB, 30 days retention.

### Error Handling
- Use `HTTPException` in API routes.
- In Celery tasks (`tasks.py`), catch exceptions, log them with `logger.exception`, and update the task status to `StateEnum.FAILED` in the shared storage.

### Security
- API key comparison uses `secrets.compare_digest` (timing-safe).
- `SecretStr` is used for `huggingface_token` (never logged).
- In production: Swagger/ReDoc/OpenAPI are disabled, HTTPS redirect middleware is enabled.

### Storage Pattern Example
The repository is stored in `app.state` during lifespan and injected via `Depends`:
```python
# src/app/main.py
@app.get("/status/{uuid}")
async def get_preprocess_status(
    uuid: str,
    repository: RedisStatusRepository = Depends(get_repository),
) -> PreprocessResponseModel:
    status_obj = repository.get_by_id(uuid)
    if not status_obj:
        raise HTTPException(status_code=404, detail="Preprocess job not found")
    return status_obj
```

## 🔌 Integration Points

- **Redis**: Used as Celery message broker AND status storage backend. A single `REDIS_URL` configures both. Managed via `docker-compose.yml` (`redis:7-alpine`).
- **Celery**: Task queue for background preprocessing. Worker runs as a separate container/process using the same Docker image with a different entrypoint.
- **Flow Preprocessing**: The heavy lifting is done by the `flow-preprocessing` package (installed via git from `The-Flow-Project/package-preprocessing`). If CV/XML logic needs changing, check if it belongs in this repo or the dependency.
- **Hugging Face**: Uses `huggingface_hub` and `HfApi` for dataset uploads. A `huggingface_token` (passed per request, not stored) is required for private repos.
- **Docker**: Multi-stage `Dockerfile` using `uv` (pinned at `0.10.11`, Python `3.12-slim-bookworm`). `docker-compose.yml` orchestrates Redis, API, and Celery Worker with health checks and resource limits. See also [STORAGE.md](STORAGE.md) for storage architecture details.
