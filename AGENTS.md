# Service TrOCR Preprocess - Agent Guidelines

This document provides essential context for AI agents working on the `service-trocr-preprocess` codebase, a FastAPI microservice for preparing TrOCR training data.

## 🏗 System Architecture

### Core Components
- **Entry Point**: `src/app/main.py` initializes the FastAPI app, middleware (CORS, RateLimit, HTTPS redirect in production), and dependency injection.
- **Worker Logic**: `src/app/worker.py` handles background processing via FastAPI `BackgroundTasks`. It orchestrates the actual preprocessing using the `flow-preprocessing` library.
- **Storage Layer**: `src/app/storage.py` provides a synchronous JSON-based storage backend.
  - **Class**: `StatusRepository` — a concrete class (not an ABC) using an in-memory `dict` with synchronous JSON file persistence.
  - **Thread Safety**: Writes are protected by a `threading.Lock`.
  - **Factory**: `create_repository(path)` creates an instance.
  - **Pattern**: Business logic accesses the repository via FastAPI dependency injection (`Depends(get_repository)`), which retrieves the singleton from `app.state`.
- **Models**: `src/app/models.py` defines Pydantic v2 models for API requests/responses and internal configuration (`Settings` via `pydantic-settings`).

### Data Flow
1. **API Request**: Authenticated via `X-API-KEY` header (timing-safe comparison with `secrets.compare_digest`).
2. **Task Creation**: Service creates a `PreprocessResponseModel` status record (`state: in_progress`) and returns it with a `request_id` immediately (HTTP 201).
3. **Background Processing**:
   - `worker.preprocess_task` is triggered as a synchronous background task (runs in a threadpool).
   - Delegates image/XML processing to `flow-preprocessing` (`ZipPreprocessor` or `HuggingFacePreprocessor`).
   - On success: updates state to `completed`, collects statistics, saves to repository.
   - On failure: updates state to `failed`, saves to repository.
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
- **Dev Server**: `uv run uvicorn src.app.main:app --reload`
- **Environment**: Ensure `.env` exists (copy from `.env.example`). Key variables:
  - `API_KEY`: Required for all authenticated endpoints.
  - `STORAGE_TYPE`: `json` (currently the only supported option).
  - `STORAGE_PATH`: Path to the JSON storage file (must have `.json` extension).
  - `JSON_EXPORT_PATH`: Path for the separate JSON export (written on shutdown).

### Testing
- No explicit `tests/` folder. Manual API testing via `/docs` (Swagger UI, development only) or `curl`.

## 🧩 Codebase Conventions

### Sync Storage, Async Routes
- API route handlers are `async` (FastAPI standard).
- The `StatusRepository` is **synchronous** — all file I/O uses standard `open()` with `threading.Lock` for thread safety.
- Background tasks (`worker.py`) are synchronous functions; FastAPI runs them in a threadpool automatically.

### Logging
- **Library**: `loguru` (not stdlib `logging`).
- **Pattern**: `from loguru import logger`.
- **Configuration**: Managed in `src/app/logging_config.py`. Logs go to console (colored, stderr) and `logs/*.log` (rotated by size).

### Error Handling
- Use `HTTPException` in API routes.
- In background tasks (`worker.py`), catch exceptions, log them with `logger.exception`, and update the task status to `StateEnum.FAILED`.

### Security
- API key comparison uses `secrets.compare_digest` (timing-safe).
- `SecretStr` is used for `huggingface_token` (never logged).
- In production: Swagger/ReDoc/OpenAPI are disabled, HTTPS redirect middleware is enabled.

### Storage Pattern Example
The repository is stored in `app.state` during lifespan and injected via `Depends`:
```python
# src/app/main.py
@app.get("/status/{uuid}")
async def get_preprocess_status_or_404(
    uuid: str,
    repository: StatusRepository = Depends(get_repository),
) -> PreprocessResponseModel:
    status_obj = repository.get_by_id(uuid)
    if not status_obj:
        raise HTTPException(status_code=404, detail="Preprocess job not found")
    return status_obj
```

## 🔌 Integration Points

- **Flow Preprocessing**: The heavy lifting is done by the `flow-preprocessing` package (installed via git from `The-Flow-Project/package-preprocessing`). If CV/XML logic needs changing, check if it belongs in this repo or the dependency.
- **Hugging Face**: Uses `huggingface_hub` and `HfApi` for dataset uploads. A `huggingface_token` (passed per request, not stored) is required for private repos.
- **Docker**: Multi-stage `Dockerfile` using `uv`. `docker-compose.yml` orchestrates the service with health checks and resource limits.
