"""
Main script Flow Preprocessing Service
"""
import time
from contextlib import asynccontextmanager
import secrets

from fastapi import (
    FastAPI,
    Body,
    Depends,
    HTTPException,
    status,
    Security,
    Request,
)
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

from loguru import logger

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app import __version__
from app.logging_config import setup_logger
from app.models import (
    Settings,
    ZipPreprocessRequestModel,
    HuggingfacePreprocessRequestModel,
    PreprocessResponseModel,
    SourceTypeEnum, StateEnum,
)
from app.tasks import preprocess_task
from app.storage import RedisStatusRepository, get_redis_repository

# ── Settings & Logging ────────────────────────────────────────────────
settings = Settings()
setup_logger(settings.LOG_LEVEL, log_files=settings.LOG_TO_FILES)

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def check_api_key(api_key: str | None = Security(api_key_header)) -> None:
    """
    Checking the API key from the request header against the environment variable.

    Args:
        api_key: API key from request header

    Raises:
        HTTPException: If API key is invalid or missing
        ValueError: If API_KEY environment variable is not set
    """
    env_api_key = settings.API_KEY

    # If API_KEY is not set, raise an error instead of allowing all requests
    if not env_api_key:
        logger.error("API_KEY environment variable is not set!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error",
        )

    if not api_key or not secrets.compare_digest(api_key, env_api_key):
        logger.warning(f"Invalid API key attempt from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager for FastAPI application lifespan events.

    Initializes the Redis status repository on startup and cleans up on shutdown.
    Uses app.state to store the repository.
    """
    logger.info(f"Initializing Redis repository at {settings.REDIS_URL}")
    app.state.repository = get_redis_repository(redis_url=settings.REDIS_URL)
    logger.info("Repository initialized successfully")

    yield

    logger.info("Shutting down service...")
    try:
        app.state.repository.close()
        logger.info("Repository closed successfully")
    except Exception as e:
        logger.error(f"Failed to close repository: {e}")
    finally:
        app.state.repository = None


app = FastAPI(
    title="FLOW-Preprocessing-Microservice",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["10/minute"],
)

# ── Middleware Stack ──────────────────────────────────────────────────
# Starlette processes middlewares in LIFO order (last added = first executed).
# Therefore, register them in REVERSE order of desired execution:
#
#   Registration order:        Execution order (incoming request):
#   1. SlowAPIMiddleware   →   3. Rate limiting
#   2. CORSMiddleware      →   2. CORS headers & preflight
#   3. HTTPSRedirect       →   1. Redirect HTTP → HTTPS (production)
# ─────────────────────────────────────────────────────────────────────

# 1) Rate Limiting (registered first → executes last among these three)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# 2) CORS (registered second → executes second)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=list(settings.CORS_ALLOWED_METHODS),
    allow_headers=list(settings.CORS_ALLOWED_HEADERS),
)

# 3) HTTPS Redirect (registered last → executes first on incoming requests)
#    Disable via HTTPS_REDIRECT=false when TLS is terminated by a reverse proxy (e.g. Traefik).
if settings.is_production and settings.HTTPS_REDIRECT:
    app.add_middleware(HTTPSRedirectMiddleware)
    logger.info("HTTPS Redirect Middleware enabled for production environment")

logger.info(f"Running in {settings.ENVIRONMENT.value}")


# Request-Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware to log all HTTP-Requests and Responses.
    """
    start_time = time.perf_counter()

    # Log Request
    logger.debug(f"→ Request: {request.method} {request.url.path}")
    logger.debug(f"  Client: {request.client.host if request.client else 'unknown'}")

    # Process request
    try:
        response = await call_next(request)

        # Calculate duration
        duration = time.perf_counter() - start_time

        # Log Response
        logger.info(
            f"← Response: {request.method} {request.url.path} "
            f"Status: {response.status_code} Duration: {duration:.3f}s"
        )

        return response
    except Exception as e:
        duration = time.perf_counter() - start_time
        logger.error(
            f"✗ Error: {request.method} {request.url.path} "
            f"Duration: {duration:.3f}s Error: {str(e)}"
        )
        raise


def _create_and_start_preprocess(
        preprocess_parameters: ZipPreprocessRequestModel | HuggingfacePreprocessRequestModel,
        repository: RedisStatusRepository,
        source_type: SourceTypeEnum,
) -> PreprocessResponseModel:
    """
    Helper function to create and dispatch a preprocess job via Celery.

    Args:
        preprocess_parameters: The preprocess parameters from the API request.
        repository: The storage repository, injected via dependency injection.
        source_type: The type of source (ZIP or HuggingFace).

    Returns:
        PreprocessResponseModel: The initial status of the newly created job.
    """
    # Extract token securely from SecretStr (never logged)
    huggingface_token = (
        preprocess_parameters.huggingface_token.get_secret_value()
        if preprocess_parameters.huggingface_token
        else None
    )

    preprocess_status = PreprocessResponseModel(
        state=StateEnum.PENDING,
        **preprocess_parameters.model_dump(
            by_alias=True,
            exclude={"huggingface_token"}
        )
    )
    logger.info(f"Preprocess status created: {preprocess_status}")

    # Save initial status (in_progress) to shared storage
    repository.save(preprocess_status)
    logger.info(
        f"Created preprocessing job {preprocess_status.request_id} for {source_type.value} source"
    )

    # Dispatch Celery task (non-blocking)
    preprocess_task.apply_async(
        kwargs={
            "status_dict": preprocess_status.model_dump(
                by_alias=True,
                mode="json",
                exclude={"huggingface_token"}
            ),
            "huggingface_token": huggingface_token,
            "source_type": source_type.value,
        },
        task_id=preprocess_status.request_id,
    )

    return preprocess_status


@app.post(
    "/preprocess/zip",
    response_description="Start a new preprocess job with a ZIP-URL.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_api_key)],
)
async def start_zip_preprocess(
        preprocess_parameters: ZipPreprocessRequestModel = Body(...),
) -> PreprocessResponseModel:
    """
    Start a new preprocess job with a ZIP-URL.

    Args:
        preprocess_parameters: The preprocess parameters.

    Returns:
        PreprocessResponseModel: The status of the newly created preprocess job.
    """
    repository = app.state.repository
    response_status = _create_and_start_preprocess(
        preprocess_parameters=preprocess_parameters,
        repository=repository,
        source_type=SourceTypeEnum.ZIP,
    )
    return response_status


@app.post(
    "/preprocess/hf",
    response_description="Start a new preprocess job with a HuggingFace RawXML repository.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_api_key)],
)
async def start_hf_preprocess(
        preprocess_parameters: HuggingfacePreprocessRequestModel = Body(...),
) -> PreprocessResponseModel:
    """
    Start a new preprocess job with a HuggingFace repository name.

    Args:
        preprocess_parameters: The preprocess parameters.

    Returns:
        PreprocessResponseModel: The status of the newly created preprocess job.
    """
    response_status = _create_and_start_preprocess(
        preprocess_parameters=preprocess_parameters,
        repository=app.state.repository,
        source_type=SourceTypeEnum.HUGGINGFACE,
    )
    return response_status


@app.get(
    "/status",
    response_description="Retrieve all preprocess statuses.",
    response_model=list[PreprocessResponseModel],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_api_key)],
)
async def get_all_preprocess_statuses(request: Request) -> list[PreprocessResponseModel]:
    """
    Retrieve all preprocess statuses.

    Returns:
        list[PreprocessResponseModel]: A list of all preprocess statuses (may be empty).
    """
    return app.state.repository.get_all()


@app.get(
    "/status/{uuid}",
    response_description="Retrieve a preprocess status by its UUID.",
    response_model=PreprocessResponseModel,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_api_key)],
)
async def get_preprocess_status(
    uuid: str,
) -> PreprocessResponseModel:
    """
    Retrieve a preprocess status by its UUID.

    Args:
        uuid: The UUID of the preprocess status to retrieve.

    Returns:
        PreprocessResponseModel: The preprocess status with the specified UUID.

    Raises:
        HTTPException: If no preprocess status with the specified UUID is found.
    """
    status_obj = app.state.repository.get_by_id(uuid)
    if not status_obj:
        logger.info(f"Preprocess job not found: {uuid}")
        raise HTTPException(status_code=404, detail="Preprocess job not found")

    return status_obj


@app.get("/health")
def health_check(request: Request):
    """
    Health check endpoint to verify the service is running.

    Returns:
        dict: Health status with service information.
    """
    logger.debug(f"Health check started from {request.client.host if request.client else 'unknown'}")
    health_data = {
        "status": "healthy",
        "service": "service-trocr-preprocess",
        "version": __version__,
    }

    # Check if repository is initialized
    try:
        if hasattr(app.state, 'repository') and app.state.repository is not None:
            health_data["repository"] = "initialized"
            health_data["storage_type"] = "redis"

            if app.state.repository.ping():
                health_data["redis"] = "connected"
            else:
                health_data["redis"] = "disconnected"
                health_data["status"] = "degraded"
        else:
            health_data["repository"] = "not_initialized"
            health_data["status"] = "degraded"
    except Exception as e:
        logger.warning(f"Health check repository error: {e}")
        health_data["repository"] = "error"
        health_data["status"] = "degraded"

    return health_data
