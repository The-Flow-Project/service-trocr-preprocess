# service-trocr-preprocess

Microservice to preprocess TrOCR training material with XML files.

## Features

- FastAPI-based REST API
- API key authentication (timing-safe)
- Redis-backed status storage
- Automatic JSON export for automation tools and HuggingFace upload
- Background task processing via Celery
- Real-time status tracking
- HTTPS redirect & docs disabled in production mode

## Installation

### Using uv (faster)

```bash
# Install uv if not already installed
pip install uv

# Install dependencies
uv sync
```

If you prefer using `pip install`, you need to create a `requirements.txt` file
first with:

```bash
uv pip compile pyproject.toml -o requirements.txt
```

## Configuration

Create a `.env` file (see `.env.example`):

```bash
# Working mode (production/development)
ENVIRONMENT=development

# API Key (required)
API_KEY=your_secret_api_key_here

# Redis connection URL (used as Celery broker and status storage)
REDIS_URL=redis://localhost:6379/0

# Log level: TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# CORS middleware settings
CORS_ALLOWED_ORIGINS='["http://localhost:3000", "http://127.0.0.1:3000"]'
CORS_ALLOWED_HEADERS='["Content-Type", "X-API-KEY"]'
CORS_ALLOWED_METHODS='["GET", "POST", "OPTIONS"]'
```

### Storage

The service uses a **Redis-backed storage backend**. All task statuses are
stored as fields in a single Redis Hash (`preprocess:statuses`).

- Human-readable JSON values per status entry
- No additional database driver needed beyond `redis-py`
- Single `REDIS_URL` configures both Celery broker and status storage

See [STORAGE.md](STORAGE.md) for detailed documentation.

## Running the Service

### Locally (without Docker)

Handy for quick iteration with hot-reload. Point `REDIS_URL` at `localhost` in
your
`.env` (see [Configuration](#configuration)) and run each process in its own
terminal:

```bash
# Start Redis
docker compose up redis -d

# Start the API server (development, hot-reload)
uv run uvicorn src.app.main:app --reload

# Start the Celery worker (separate terminal)
cd src && uv run celery -A app.tasks worker --loglevel=debug
```

### With Docker Compose

The stack is split across three files so the same core definition serves both
dev and prod:

| File                          | Role                                                                                          |
|-------------------------------|-----------------------------------------------------------------------------------------------|
| `docker-compose.yml`          | Core services — Redis, API, Celery worker. The app port is **not** published here.            |
| `docker-compose.override.yml` | **Local dev only.** Auto-merged on a bare `docker compose up`; publishes the app on `:8000`.  |
| `docker-compose.traefik.yml`  | **Prod overlay** for a shared [Traefik](https://traefik.io) proxy (TLS + routing via labels). |

First-time setup for any variant:

```bash
cp .env.example .env
nano .env            # set API_KEY (required); set APP_DOMAIN + HTTPS_REDIRECT=false for Traefik
```

#### 1. Local development (default)

A bare `up` auto-merges `docker-compose.override.yml`, so the API is reachable
directly:

```bash
docker compose up -d --build          # Redis + API + Celery worker

docker compose ps                     # health/status
curl http://localhost:8000/health
docker compose logs -f                # all services
docker compose logs celery-worker -f  # just the worker
```

The app is then at http://localhost:8000 (interactive docs at `/docs` in
development mode).

#### 2. Production behind Traefik

Passing explicit `-f` flags **disables the override**, so no host port is
published — traffic
only reaches the app through Traefik (routed by the `APP_DOMAIN` label).
Requires an external
`traefik-public` network and a running Traefik instance:

```bash
docker compose -f docker-compose.yml -f docker-compose.traefik.yml up -d --build
```

Drop `--build` if you build/push the image in CI and only pull it on the host
(`pull_policy` is `missing`). If you also need to run the Traefik proxy itself,
see
`docker-compose.traefik-proxy.yml`.

**Health check:** the API service defines a Docker health check that polls
`/health` every
30s (unhealthy after 3 failures, 30s start grace). It is scoped to the API
only — the Celery
worker runs no HTTP server and is intentionally left without one.

## API Usage

### Start Preprocessing Job

```bash
# With ZIP file
curl -X POST http://localhost:8000/preprocess/zip \
  -H "X-API-KEY: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "zip_url": "https://example.com/data.zip",
    "huggingface_token": "hf_...",
    "huggingface_target_repo_name": "username/dataset-name"
  }'

# With HuggingFace repository
curl -X POST http://localhost:8000/preprocess/hf \
  -H "X-API-KEY: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "huggingface_source_repo_name": "username/raw-xml-dataset",
    "huggingface_token": "hf_...",
    "huggingface_target_repo_name": "username/processed-dataset"
  }'
```

### Check Status

```bash
# Get all statuses
curl -H "X-API-KEY: your_api_key_here" \
  http://localhost:8000/status

# Get specific status by ID
curl -H "X-API-KEY: your_api_key_here" \
  http://localhost:8000/status/{request_id}
```

### Health Check

```bash
# No API key required
curl http://localhost:8000/health
```

## Documentation

- [Storage Documentation](STORAGE.md) - Detailed storage system documentation
- API Documentation: http://localhost:8000/docs (development mode only)

## License

MIT
