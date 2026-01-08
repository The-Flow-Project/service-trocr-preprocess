# Storage System Documentation

## Overview

The service provides **two storage options** for persisting preprocessing status:

1. **SQLite** (recommended) - Thread-safe, performant, with automatic JSON export
2. **JSON** - Directly readable, with file locking against race conditions

## 🎯 Why this solution?

- ✅ Thread-safe and process-safe
- ✅ ACID transactions (with SQLite)
- ✅ Fast queries with indexes
- ✅ Automatic JSON export for automation tools
- ✅ Compatible with HuggingFace upload

---

## 🏗️ Architecture

```
┌─────────────────────┐
│   FastAPI Service   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  StatusRepository   │  (Abstract Interface)
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐  ┌──────────┐
│ SQLite  │  │   JSON   │
│  (.db)  │  │  (.json) │
└────┬────┘  └──────────┘
     │
     │ auto-export
     ▼
┌──────────────────────┐
│  JSON Export         │
│  (for Automation)    │
└──────────────────────┘
```

---

## 🔧 Configuration

### Environment Variables

```bash
# .env
API_KEY=your_secret_api_key

# Storage type: "sqlite" or "json"
STORAGE_TYPE=sqlite

# Path to storage file
STORAGE_PATH=./preprocessing-status.db

# Path for JSON export (for automation tools)
JSON_EXPORT_PATH=./preprocessing-status.json
```

---

When using SQLite, a JSON file is automatically created for your automation tool:

Automatic export on:

1. Service startup
2. Service shutdown
3. GET /status request

```bash
# Get the current status
curl -H "X-API-KEY: your_key" http://localhost:8000/status
```

**Recommendation:**

- **< 100 entries:** JSON is okay
- **\> 100 entries:** SQLite significantly better
- **Production:** Always SQLite


