# Service TrOCR Preprocess - Agent Guidelines

This document provides essential context for AI agents working on the `service-trocr-preprocess` codebase, a FastAPI microservice for preparing TrOCR training data.

## 🏗 System Architecture

### Core Components
- **Entry Point**: `src/app/main.py` initializes the FastAPI app, middleware (CORs, RateLimit), and dependency injection.
- **Worker Logic**: `src/app/worker.py` handles background processing via FastAPI `BackgroundTasks`. It orchestrates the actual preprocessing using the `flow-preprocessing` library.
- **Storage Layer**: `src/app/storage.py` implements the Repository pattern.
  - **Interface**: `StatusRepository` (Abstract Base Class).
  - **Implementations**: `SQLModelStatusRepository` (SQLite/Async) and `JSONStatusRepository` (Flat file/Locking).
  - **Pattern**: Business logic interacts *only* with the abstract interface, never directly with DB drivers.
- **Models**: `src/app/models.py` defines Pydantic models for API requests/responses and internal configuration (`Settings`).

### Data Flow
1. **API Request**: Authenticated via `X-API-KEY`.
2. **Task Creation**: Service creates a status record (queued) and returns a `request_id` immediately.
3. **Background Processing**:
   - `worker.process_task` is triggered asynchronously.
   - Updates status to `running`.
   - Delegates image/XML processing to `flow-preprocessing` (external lib).
   - Optionally uploads results/status to Hugging Face.
   - Updates status to `finished` or `failed`.

## 🛠 Developer Workflows & Commands

### dependency Management
The project uses `uv` for fast package management.
- **Install**: `uv sync` (creates venv and installs deps).
- **Add Dependency**: `uv add <package>`.
- **Export Requirements**: `uv pip compile pyproject.toml -o requirements.txt` (Required for Docker compatibility if not using uv in container).

### Running Locally
- **Dev Server**: `uv run uvicorn src.app.main:app --reload`
- **Environment**: Ensure `.env` exists (copy from `.env.example`). Key variables:
  - `API_KEY`: Required for all requests.
  - `STORAGE_TYPE`: `sqlite` (default) or `json`.

### Testing
- No explicit `tests/` folder visible in root. Check `src/app` for inline tests or assume manual API testing via `docs` (/docs) or `curl`.

## 🧩 Codebase Conventions

### Async First
- Use `async/await` for all I/O bound operations (DB, File, Network).
- Use `aiofiles` for file I/O and `aiosqlite` (via SQLModel) for database interactions.

### Logging
- **Library**: `loguru` (not stdlib `logging`).
- **Pattern**: `from loguru import logger`.
- **Configuration**: Managed in `src/app/logging_config.py`. Logs go to console (colored) and `logs/*.log` (rotated).

### Error Handling
- Use `HTTPException` in API routes.
- In background tasks (`worker.py`), catch exceptions, log them with `logger.error`, and update the task status to `StateEnum.FAILED`. Do not crash the worker thread.

### Storage Pattern Example
When accessing data, use the dependency injection:
```python
# src/app/main.py
@app.get("/status/{request_id}")
async def get_status(
    request_id: str, 
    repo: StatusRepository = Depends(get_repository)
):
    return await repo.get(request_id)
```

## 🔌 Integration Points

- **Flow Preprocessing**: The heavy lifting is done by the `flow-preprocessing` package. If CV logic needs changing, check if it's in this repo or the dependency.
- **Hugging Face**: Uses `huggingface_hub` and `HfApi` for dataset uploads. Requires `HUGGINGFACE_TOKEN` if interacting with private repos.
- **Docker**: `Dockerfile` is present. `docker-compose.yml` orchestrates the service.

