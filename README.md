# service-trocr-preprocess

Microservice to preprocess TrOCR training material with XML files.

## Features

- 🚀 FastAPI-based REST API
- 🔒 API key authentication
- 📊 Two storage options: SQLite (recommended) or JSON
- 📤 Automatic JSON export for automation tools and HuggingFace upload
- 🔄 Background task processing
- 📈 Real-time status tracking
- ⚡ Thread-safe operations

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
````

## Configuration

Create a `.env` file (see `.env.example`):

```bash
# API Key (required)
API_KEY=your_secret_api_key_here

# Storage type: "sqlite" (recommended) or "json"
STORAGE_TYPE=sqlite

# Storage file path
STORAGE_PATH=./preprocessing-status.db

# JSON export path (for automation tools & HuggingFace)
JSON_EXPORT_PATH=./preprocessing-status.json
```

### Storage Options

**SQLite (recommended for production):**
- ✅ Thread-safe, no race conditions
- ✅ Fast with indexes
- ✅ Automatic JSON export for automation
- ✅ Single file, easy to backup

**JSON (good for development):**
- ✅ Human-readable
- ✅ Easy to debug
- ✅ File-locking prevents race conditions

See [STORAGE.md](STORAGE.md) for detailed documentation.

## Running the Service

```bash
# Set environment variables
export API_KEY=your_api_key_here
export STORAGE_TYPE=sqlite
export STORAGE_PATH=./preprocessing-status.db

# Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
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

# Run container with health check
docker run -d \
  --name trocr-preprocess \
  -p 8000:8000 \
  -v $(pwd)/data:/data \
  -e API_KEY=your_api_key_here \
  -e STORAGE_TYPE=sqlite \
  -e STORAGE_PATH=/data/preprocessing-status.db \
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

## Documentation

- [Storage Documentation](STORAGE.md) - Detailed storage system documentation
- API Documentation: http://localhost:8000/docs (when running)

## License

MIT

