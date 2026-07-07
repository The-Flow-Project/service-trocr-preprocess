# ================================
# Stage 1: Builder
# ================================
FROM astral/uv:python3.12-bookworm-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/root/.cache/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock /app/

# CPU torch comes straight from the lock (pinned to the cpu index in pyproject.toml).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace

# ── GPU escape hatch — NOT needed for preprocessing ───────────
# To build a GPU image: pass --build-arg TORCH_VARIANT=cu126 and uncomment.
# (Re-installs torch from the CUDA index WITH deps so the bundled nvidia-*-cu12
#  libs land in the venv; runtime stays on plain python:3.12-slim.)
# ARG TORCH_VERSION=2.7.1
# ARG TORCHVISION_VERSION=0.22.1
# ARG TORCH_VARIANT=cpu
# RUN --mount=type=cache,target=/root/.cache/uv \
#     if [ "${TORCH_VARIANT}" != "cpu" ]; then \
#         uv pip install \
#             "torch==${TORCH_VERSION}+${TORCH_VARIANT}" \
#             "torchvision==${TORCHVISION_VERSION}+${TORCH_VARIANT}" \
#             --index-url "https://download.pytorch.org/whl/${TORCH_VARIANT}"; \
#     fi

# ================================
# Stage 2: Runtime
# ================================
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

# libgomp1 = OpenMP, needed by CPU torch; the rest are for OpenCV/image I/O
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/*

# Run as an unprivileged user (both the API and the celery worker use this image).
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser ./src /app/src
RUN chown appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]