# Storage System Documentation

## Overview

The service uses a **JSON-based storage backend** for persisting preprocessing status. All task statuses are held in memory (dictionary) and synchronously persisted to a single JSON file on every write. A `threading.Lock` ensures thread-safety when multiple background tasks run concurrently.

## 🎯 Why this solution?

- ✅ Thread-safe via `threading.Lock`
- ✅ Human-readable — statuses can be inspected directly in the JSON file
- ✅ Zero external dependencies (no database driver required)
- ✅ Automatic JSON export for automation tools on shutdown
- ✅ Compatible with HuggingFace status upload
- ✅ Single file, easy to backup and inspect

---

## 🏗️ Architecture

```
┌─────────────────────┐
│   FastAPI Service    │
│      (main.py)       │
└──────────┬──────────┘
           │  Depends(get_repository)
           ▼
┌─────────────────────┐
│  StatusRepository    │  (Concrete class, in-memory dict + JSON persistence)
│  - _data: Dict       │  Thread-safe writes via threading.Lock
│  - json_path: Path   │
└──────────┬──────────┘
           │  _save_to_file() on every save()
           ▼
┌──────────────────────┐
│  preprocessing-      │
│  status.json         │  Primary storage file
└──────────────────────┘
           ▲
           │  export_to_json() on shutdown
           │  (writes back to primary storage file at STORAGE_PATH)

```

---

## 🔧 Configuration

### Environment Variables

```bash
# .env

# API Key (required)
API_KEY=your_secret_api_key

# Storage type (currently only "json" is supported)
STORAGE_TYPE=json

# Path to the primary JSON storage file (also used for shutdown export)
STORAGE_PATH=./preprocessing-status.json

# Log level
LOG_LEVEL=INFO
```

> **Note:** `STORAGE_PATH` must have a `.json` extension. The service validates this on startup and will raise an error otherwise. The shutdown JSON export is also written to this same path.

---

## 📦 Storage File Format

The JSON file contains an array of status objects:

```json
[
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
]
```

---

## 🔄 Lifecycle

1. **Startup**: `StatusRepository` loads existing data from `STORAGE_PATH` into memory.
2. **Runtime**: Each `save()` call updates the in-memory dict and writes the entire state to the JSON file (protected by `threading.Lock`).
3. **Shutdown**: The service exports the final state to `JSON_EXPORT_PATH` via `export_to_json()`.

---

## 🔒 Thread Safety

Background preprocessing tasks run in separate threads (via FastAPI `BackgroundTasks`). The `StatusRepository.save()` method uses a `threading.Lock` to prevent concurrent writes from corrupting the JSON file:

```python
def save(self, status: PreprocessResponseModel) -> None:
    with self._lock:
        self._data[status.request_id] = status
        self._save_to_file()
```

Read operations (`get_by_id`, `get_all`) also acquire `self._lock` before accessing the in-memory dict, ensuring thread-safe and consistent reads alongside writes.

---

## ⚠️ Limitations

- **Scale**: The entire status list is serialized and written on every `save()`. For very large numbers of jobs (hundreds+), this can become slow. For most use cases this is not a concern.
- **No query filtering**: All statuses are loaded into memory. Filtering is done in Python, not at the storage level.
- **Single-process only**: The file-based approach does not support multi-process deployments. Use a single worker process or an external database for multi-process setups.
