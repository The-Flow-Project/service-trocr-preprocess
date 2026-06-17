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

If you prefer using `pip install`, you need to create a `requirements.txt` file first with:

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

The service uses a **Redis-backed storage backend**. All task statuses are stored as fields in a single Redis Hash (`preprocess:statuses`).

- Human-readable JSON values per status entry
- No additional database driver needed beyond `redis-py`
- Single `REDIS_URL` configures both Celery broker and status storage

See [STORAGE.md](STORAGE.md) for detailed documentation.

## Running the Service

```bash
# Start Redis
docker compose up redis -d

# Start the API server (development)
uv run uvicorn src.app.main:app --reload

# Start the Celery worker (separate terminal)
cd src && uv run celery -A app.tasks worker --loglevel=debug
```

### Using Docker

**With Docker Compose (recommended):**

```bash
# Setup environment
cp .env.example .env
nano .env  # Set your API_KEY

# Start all services (Redis, API, Celery Worker)
docker compose up --build

# Check health status
docker compose ps
curl http://localhost:8000/health

# View logs
docker compose logs -f

# Follow Celery worker logs
docker compose logs celery-worker -f
```

**Health Check:**

- Automatic health monitoring built into Docker
- Checks `/health` endpoint every 30 seconds
- Container marked as unhealthy after 3 failed checks

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
