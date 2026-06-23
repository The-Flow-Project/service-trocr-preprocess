# CUDA_RUNTIME_IMAGE must be declared before the first FROM to be usable in FROM statements
ARG CUDA_RUNTIME_IMAGE=nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04

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

# AIDEV-NOTE: --no-deps swaps only torch/torchvision wheels without touching other packages from uv sync
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "${TORCH_VARIANT}" != "cpu" ]; then \
        echo "Installing GPU torch variant: ${TORCH_VARIANT}" && \
        uv pip install \
            "torch==${TORCH_VERSION}+${TORCH_VARIANT}" \
            "torchvision==${TORCHVISION_VERSION}+${TORCH_VARIANT}" \
            --index-url "https://download.pytorch.org/whl/${TORCH_VARIANT}" \
            --no-deps; \
    fi

# ================================
# Stage 2a: CPU Runtime
# ================================
FROM python:3.12-slim-bookworm AS runtime-cpu

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

# ================================
# Stage 2b: GPU Runtime
# ================================
# AIDEV-NOTE: Ubuntu 22.04 (CUDA base) ships Python 3.10; 3.12 is installed via deadsnakes PPA
FROM ${CUDA_RUNTIME_IMAGE} AS runtime-gpu

ARG DEBIAN_FRONTEND=noninteractive
ARG CUDA_CUPTI_PKG_VERSION=12-4

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    cuda-cusparse-12-6 \
    cuda-cusparse-dev-12-6 \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY ./src /app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
