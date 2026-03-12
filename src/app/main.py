"""
Main script Flow Preprocessing Service
"""
import time
from typing import List
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Body,
    Depends,
    HTTPException,
    status,
    Security,
    BackgroundTasks,
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

from .models import (
    Settings,
    ZipPreprocessRequestModel,
    HuggingfacePreprocessRequestModel,
    PreprocessResponseModel,
    SourceTypeEnum,
)
from .worker import preprocess_task
from .storage import create_repository, StatusRepository
from .logging_config import setup_logger

# Configure loguru logger
settings = Settings()
setup_logger(level=settings.LOG_LEVEL.value)

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

# Storage configuration
STORAGE_PATH = settings.STORAGE_PATH
JSON_EXPORT_PATH = settings.JSON_EXPORT_PATH


def get_repository() -> StatusRepository:
    """
    Dependency function to get the repository from app.state.

    Returns:
        StatusRepository: The initialized repository instance.

    Raises:
        RuntimeError: If repository is not initialized.
    """
    if not hasattr(app.state, 'repository') or app.state.repository is None:
        logger.error("Repository not initialized!")
        raise RuntimeError("Repository not initialized. Check lifespan configuration.")
    return app.state.repository


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

    if not api_key or api_key != env_api_key:
        logger.warning(f"Invalid API key attempt from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager for FastAPI application lifespan events.

    Initializes the storage repository on startup and exports to JSON on shutdown.
    Uses app.state to store the repository.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: This function does not yield any value.
    """
    # Startup - Store repository in app.state
    logger.info(f"Initializing repository at {STORAGE_PATH}")
    app.state.repository = create_repository(path=STORAGE_PATH)
    logger.info("Repository initialized successfully")

    yield

    # Shutdown - Export final status and close repository
    logger.info("Shutting down service...")

    try:
        app.state.repository.export_to_json(JSON_EXPORT_PATH)
        logger.info(f"Exported final status to {JSON_EXPORT_PATH}")
    except Exception as e:
        logger.error(f"Failed to export to JSON on shutdown: {e}")

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
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per day", "10/minute"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=list(settings.CORS_ALLOWED_METHODS),
    allow_headers=list(settings.CORS_ALLOWED_HEADERS),
)

if settings.is_production:
    # HTTPS Redirect Middleware
    app.add_middleware(HTTPSRedirectMiddleware)
    logger.info("HTTPS Redirect Middleware enabled for production environment")

    # Disable OpenAPI docs in production
    app.docs_url = None
    app.redoc_url = None
    app.openapi_url = None
    logger.info("API documentation disabled in production")

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


@app.post(
    "/preprocess/zip",
    response_description="Start a new preprocess job with a ZIP-URL.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_api_key)],
)
async def start_zip_preprocess(
        background_tasks: BackgroundTasks,
        preprocess_parameters: ZipPreprocessRequestModel = Body(...),
        repository: StatusRepository = Depends(get_repository),
) -> dict:
    """
    Start a new preprocess job with a ZIP-URL.

    Args:
        background_tasks: The background tasks object, injected by FastAPI.
        preprocess_parameters: The preprocess parameters.
        repository: The storage repository, injected via dependency injection.

    Returns:
        dict: Response with message and status information.
    """
    # Extract token securely from SecretStr (never logged)
    huggingface_token = (
        preprocess_parameters.huggingface_token.get_secret_value()
        if preprocess_parameters.huggingface_token
        else None
    )

    preprocess_status = PreprocessResponseModel(
        **preprocess_parameters.model_dump(
            by_alias=True,
            exclude={"huggingface_token"}
        )
    )
    logger.info(f"Preprocess status created: {preprocess_status}")
    # Save initial status
    repository.save(preprocess_status)
    logger.info(
        f"Created preprocessing job {preprocess_status.request_id} for ZIP source"
    )

    # Start the preprocess job
    background_tasks.add_task(
        preprocess_task,
        repository=repository,
        huggingface_token=huggingface_token,
        created_status=preprocess_status,
        source_type=SourceTypeEnum.ZIP,
    )

    return {
        "message": "Preprocess job started",
        **preprocess_status.model_dump(by_alias=True),
    }


@app.post(
    "/preprocess/hf",
    response_description="Start a new preprocess job with a HuggingFace RawXML repository.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_api_key)],
)
async def start_hf_preprocess(
        background_tasks: BackgroundTasks,
        preprocess_parameters: HuggingfacePreprocessRequestModel = Body(...),
        repository: StatusRepository = Depends(get_repository),
) -> dict:
    """
    Start a new preprocess job with a HuggingFace repository name.

    Args:
        background_tasks: The background tasks object, injected by FastAPI.
        preprocess_parameters: The preprocess parameters.
        repository: The storage repository, injected via dependency injection.

    Returns:
        dict: Response with message and status information.
    """
    # Extract token securely from SecretStr (never logged)
    huggingface_token = (
        preprocess_parameters.huggingface_token.get_secret_value()
        if preprocess_parameters.huggingface_token
        else None
    )

    preprocess_status = PreprocessResponseModel(
        **preprocess_parameters.model_dump(
            by_alias=True,
            exclude={"huggingface_token"}
        )
    )

    # Save initial status
    repository.save(preprocess_status)
    logger.info(
        f"Created preprocessing job {preprocess_status.request_id} "
        f"for HuggingFace source"
    )

    # Start the preprocess job
    background_tasks.add_task(
        preprocess_task,
        repository=repository,
        huggingface_token=huggingface_token,
        created_status=preprocess_status,
        source_type=SourceTypeEnum.HUGGINGFACE,
    )

    return {
        "message": "Preprocess job started",
        **preprocess_status.model_dump(by_alias=True),
    }


@app.get(
    "/status",
    response_description="Retrieve all preprocess statuses.",
    response_model=List[PreprocessResponseModel],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_api_key)],
)
async def get_all_preprocess_statuses_or_404(
        repository: StatusRepository = Depends(get_repository),
) -> List[PreprocessResponseModel]:
    """
    Retrieve all preprocess statuses.

    Args:
        repository: The storage repository, injected via dependency injection.

    Returns:
        List[PreprocessResponseModel]: A list of all preprocess statuses.
    Raises:
        HTTPException: If no preprocess statuses are found.
    """
    data = repository.get_all()
    if len(data) == 0:
        logger.info("No preprocess statuses found")
        raise HTTPException(status_code=404, detail="No preprocess jobs found")

    return data


@app.get(
    "/status/{uuid}",
    response_description="Retrieve a preprocess status by its UUID.",
    response_model=PreprocessResponseModel,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_api_key)],
)
async def get_preprocess_status_or_404(
        uuid: str,
        repository: StatusRepository = Depends(get_repository),
) -> PreprocessResponseModel:
    """
    Retrieve a preprocess status by its UUID.

    Args:
        uuid: The UUID of the preprocess status to retrieve.
        repository: The storage repository, injected via dependency injection.

    Returns:
        PreprocessResponseModel: The preprocess status with the specified UUID.

    Raises:
        HTTPException: If no preprocess status with the specified UUID is found.
    """
    status_obj = repository.get_by_id(uuid)
    if not status_obj:
        logger.info(f"Preprocess job not found: {uuid}")
        raise HTTPException(status_code=404, detail="Preprocess job not found")

    return status_obj


@app.get("/health")
@limiter.limit("4/minute")
def health_check(request: Request):
    """
    Health check endpoint to verify the service is running.

    Returns:
        dict: Health status with service information.
    """
    logger.info(f"Health check started from {request.client.host}")
    health_data = {
        "status": "healthy",
        "service": "service-trocr-preprocess",
        "version": "0.1.0",
    }

    # Check if repository is initialized
    try:
        if hasattr(app.state, 'repository') and app.state.repository is not None:
            health_data["repository"] = "initialized"
            health_data["storage_type"] = "json"
        else:
            health_data["repository"] = "not_initialized"
            health_data["status"] = "degraded"
    except Exception as e:
        logger.warning(f"Health check repository error: {e}")
        health_data["repository"] = "error"
        health_data["status"] = "degraded"

    return health_data
