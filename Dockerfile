# ================================
# Stage 1: Builder
# ================================
FROM python:3.12-slim-bookworm AS builder

# Set environment variables for build
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/root/.cache/uv

# Torch variant: "cpu" (default, ~300 MB) or "cu128" / "cu126" / "cu124" (CUDA, ~2.5 GB).
# Must match the CUDA version installed on the host (check: nvidia-smi).
# Example: docker compose build --build-arg TORCH_VARIANT=cu128
ARG TORCH_VARIANT=cpu

# Install uv (pinned version for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

# Install build dependencies (only in builder stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files (both pyproject.toml and uv.lock)
COPY pyproject.toml uv.lock /app/

# Install dependencies with uv - way faster!
# --no-install-workspace: Installs only dependencies, not the local package
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace

# Reinstall torch/torchvision from the CUDA index if a GPU variant is requested.
# Uses --no-deps to only swap the torch wheels without touching other packages.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "${TORCH_VARIANT}" != "cpu" ]; then \
        echo "Installing GPU torch variant: ${TORCH_VARIANT}" && \
        uv pip install \
            "torch==2.7.1+${TORCH_VARIANT}" \
            "torchvision==0.22.1+${TORCH_VARIANT}" \
            --index-url "https://download.pytorch.org/whl/${TORCH_VARIANT}" \
            --no-deps; \
    fi

# ================================
# Stage 2: Runtime
# ================================
FROM python:3.12-slim-bookworm AS runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

# Install only runtime dependencies (minimal!)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY ./src /app/src

# Expose port
EXPOSE 8000

# Health check configuration
# Checks every 30 seconds if the /health endpoint responds
# Timeout after 10 seconds
# 3 attempts before marking container as unhealthy
# Starts after 30 seconds (gives service time to start)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
