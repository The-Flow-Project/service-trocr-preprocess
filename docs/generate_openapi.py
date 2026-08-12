"""Export the FastAPI OpenAPI schema for the static Redoc-rendered API reference.

Written to docs/_extra/, which conf.py copies verbatim into the built site
(html_extra_path) alongside docs/_extra/api-reference.html.

AIDEV-NOTE: importing app.main eagerly constructs the shared Redis status
repository (see app/celery_app.py), which pings Redis at import time. This
script therefore needs a reachable REDIS_URL, same as the Sphinx build itself.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.main import app

if __name__ == "__main__":
    output_path = Path(__file__).parent / "_extra" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(app.openapi(), indent=2))
    print(f"Wrote OpenAPI schema to {output_path}")
