# ================================
# Stage 1: Builder (shared)
# ================================
FROM astral/uv:python3.12-bookworm-slim AS builder

ARG TORCH_VERSION=2.7.1
ARG TORCHVISION_VERSION=0.22.1
ARG TORCH_VARIANT=cpu

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/root/.cache/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace

# AIDEV-NOTE: GPU builds reinstall torch from the CUDA index WITH deps (no --no-deps),
# so the wheel's bundled nvidia-*-cu12 CUDA libs land in the venv. This is what lets the
# runtime stage stay on plain python:3.12-slim — no CUDA base image needed; only the host
# NVIDIA driver, injected at runtime by the NVIDIA Container Toolkit (see docker-compose.gpu.yml).
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "${TORCH_VARIANT}" != "cpu" ]; then \
        echo "Installing GPU torch variant: ${TORCH_VARIANT}" && \
        uv pip install \
            "torch==${TORCH_VERSION}+${TORCH_VARIANT}" \
            "torchvision==${TORCHVISION_VERSION}+${TORCH_VARIANT}" \
            --index-url "https://download.pytorch.org/whl/${TORCH_VARIANT}"; \
    fi

# ================================
# Stage 2: Runtime (CPU or GPU)
# ================================
# AIDEV-NOTE: One runtime stage for both CPU and GPU. Whether this image is CPU- or
# GPU-capable is decided entirely by the TORCH_VARIANT build arg above (which torch wheel
# got baked into /app/.venv) — not by the base image. GPU device access is granted at
# runtime via compose `deploy.resources.reservations.devices` (docker-compose.gpu.yml).
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

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

COPY --from=builder /app/.venv /app/.venv
COPY ./src /app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
