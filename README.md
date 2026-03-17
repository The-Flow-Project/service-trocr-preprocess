# service-trocr-preprocess

Microservice to preprocess TrOCR training material with XML files.

## Features

- 🚀 FastAPI-based REST API
- 🔒 API key authentication (timing-safe)
- 📊 JSON-based status storage with thread-safe persistence
- 📤 Automatic JSON export for automation tools and HuggingFace upload
- 🔄 Background task processing
- 📈 Real-time status tracking
- ⚡ Thread-safe operations via `threading.Lock`
- 🛡️ HTTPS redirect & docs disabled in production mode

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

# Storage type (currently only "json" is supported)
STORAGE_TYPE=json

# Storage file path (must have .json extension)
STORAGE_PATH=./preprocessing-status.json

# JSON export uses the same file as STORAGE_PATH (e.g. for automation tools)

# Log level: TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# CORS middleware settings
CORS_ALLOWED_ORIGINS='["http://localhost:3000", "http://127.0.0.1:3000"]'
CORS_ALLOWED_HEADERS='["Content-Type", "X-API-KEY"]'
CORS_ALLOWED_METHODS='["GET", "POST", "OPTIONS"]'
```

### Storage

The service uses a **JSON-based storage backend**. All task statuses are held in an in-memory dictionary and persisted to a JSON file on every write. Concurrent writes from background tasks are protected by a `threading.Lock`.

- ✅ Human-readable — inspect statuses directly in the JSON file
- ✅ Thread-safe via `threading.Lock`
- ✅ Zero external dependencies (no database driver needed)
- ✅ Single file, easy to backup

See [STORAGE.md](STORAGE.md) for detailed documentation.

## Running the Service

```bash
# Set environment variables
export API_KEY=your_api_key_here

# Start the service (development)
uv run uvicorn src.app.main:app --reload

# Or without uv
uvicorn src.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Using Docker

**With Docker Compose (recommended):**

```bash
# Setup environment
cp .env.example .env
nano .env  # Set your API_KEY

# Start service
docker-compose up -d

# Check health status
docker-compose ps
curl http://localhost:8000/health

# View logs
docker-compose logs -f
```

**With Dockerfile only:**

```bash
# Build image
docker build -t service-trocr-preprocess .

# Run container
docker run -d \
  --name trocr-preprocess \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  -e API_KEY=your_api_key_here \
  -e STORAGE_PATH=/data/preprocessing-status.json \
  -e JSON_EXPORT_PATH=/data/preprocessing-status.json \
  service-trocr-preprocess

# Check health status
docker ps
```

**Health Check:**

- ✅ Automatic health monitoring built into Docker
- ✅ Checks `/health` endpoint every 30 seconds
- ✅ Container marked as unhealthy after 3 failed checks

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

