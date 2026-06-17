"""
Models for the preprocessing service.
"""
from datetime import datetime, UTC
from enum import Enum
from typing import Annotated
from uuid import uuid4

from pydantic import (
    Field,
    ConfigDict,
    HttpUrl,
    SecretStr,
    field_validator,
)

from pydantic_settings import BaseSettings, SettingsConfigDict
from flow_preprocessing import PreprocessorBaseConfig

__all__ = [
    "LogLevelEnum",
    "SourceTypeEnum",
    "EnvironmentEnum",
    "Settings",
    "StateEnum",
    "PreprocessBaseModel",
    "PreprocessRequestModel",
    "ZipPreprocessRequestModel",
    "HuggingfacePreprocessRequestModel",
    "PreprocessResponseModel",
]


class LogLevelEnum(str, Enum):
    """Enum for loguru log levels."""
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SourceTypeEnum(str, Enum):
    """
    Enum class for different source types.
    """
    ZIP = "zip"
    HUGGINGFACE = "huggingface"


class EnvironmentEnum(str, Enum):
    """
    Enum class for different environments.
    """
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Settings for the preprocessing service.
    """
    API_KEY: Annotated[str | None, Field(
        default=None,
        alias="api_key",
        description="API key for authenticating requests to the preprocessing service."
                    "If not set, no authentication is required.",
        title="API-Key",
        examples=["ThisIsASecure_API_Key1337!"],
    )]

    ENVIRONMENT: Annotated[EnvironmentEnum, Field(
        default=EnvironmentEnum.DEVELOPMENT,
        alias="environment",
        description="Environment in which the preprocessing service is running."
                    "Options are 'development' and 'production'."
                    "In 'development' mode, some security middlewares may be disabled for easier testing.",
        title="Environment",
    )]

    # Redis / Celery Settings
    REDIS_URL: Annotated[str, Field(
        default="redis://localhost:6379/0",
        alias="redis_url",
        description="Redis connection URL used as Celery broker and status storage backend.",
        title="Redis-URL",
        examples=["redis://localhost:6379/0", "redis://redis:6379/0"],
    )]

    # Logging
    LOG_LEVEL: Annotated[LogLevelEnum, Field(
        default=LogLevelEnum.INFO,
        alias="log_level",
        description="Log level for the preprocessing service.",
        title="Log-Level",
    )]
    LOG_TO_FILES: Annotated[bool, Field(
        default=False,
        alias="log_to_files",
        description="Whether to log to files or not.",
        title="Log-To-Files",
    )]

    # HTTPS Redirect
    HTTPS_REDIRECT: Annotated[bool, Field(
        default=True,
        alias="https_redirect",
        description="Whether to enable the HTTPS redirect middleware. "
                    "Set to False when running behind a reverse proxy (e.g. Traefik) "
                    "that handles TLS termination to avoid redirect loops.",
        title="HTTPS-Redirect",
    )]

    # CORS Settings
    CORS_ALLOWED_ORIGINS: Annotated[set[str], Field(
        default={"*"},
        alias="cors_allowed_origins",
        description="Set of allowed origins for CORS. All allowed by default.",
        title="CORS-Allowed-Origins",
    )]
    CORS_ALLOWED_HEADERS: Annotated[set[str], Field(
        default=["*"],
        alias="cors_allowed_headers",
        description="Set of allowed headers for CORS. All allowed by default.",
        title="CORS-Allowed-Headers",
    )]
    CORS_ALLOWED_METHODS: Annotated[set[str], Field(
        default=["GET", "POST", "OPTIONS"],
        alias="cors_allowed_methods",
        description="Set of allowed methods for CORS. GET and POST allowed by default.",
        title="CORS-Allowed-Methods",
    )]
    CELERY_TASK_TIME_LIMIT: Annotated[int, Field(
        default=3600,
        alias="celery_task_time_limit",
        description="Time limit for the celery task in seconds.",
        title="Celery-Task-Timelimit",
    )]
    CELERY_TASK_SOFT_TIME_LIMIT: Annotated[int, Field(
        default=3300,
        alias="celery_task_soft_time_limit",
        description="Soft time limit for the celery task in seconds.",
        title="Celery-Task-Soft-Timelimit",
    )]

    @property
    def is_production(self) -> bool:
        """
        Check if the environment is production.
        """
        return self.ENVIRONMENT == EnvironmentEnum.PRODUCTION

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


class StateEnum(str, Enum):
    """
    Enum class for the state of the process.
    """
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    COMPLETED = "completed"


class PreprocessBaseModel(PreprocessorBaseConfig):
    """
    Base model for preprocess requests (zip and huggingface) and responses.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )


class PreprocessRequestModel(PreprocessBaseModel):
    huggingface_token: Annotated[SecretStr | None, Field(
        default=None,
        alias="huggingface_token",
        description="Hugging Face token to authenticate with the Hugging Face API."
                    "Required if 'huggingface_target_repo_name' is provided."
                    "This token is encrypted in transit via HTTPS and never stored in logs.",
        title="HuggingFace-Token",
        examples=["hf_1234567890"],
    )]


class ZipPreprocessRequestModel(PreprocessRequestModel):
    zip_url: Annotated[HttpUrl, Field(
        alias="zip_url",
        description="URL of the ZIP file containing the data export to preprocess.",
        title="Zip-URL",
        serialization_alias="source",
        examples=["https://example.com/path/to/your/export_data.zip"],
    )]


class HuggingfacePreprocessRequestModel(PreprocessRequestModel):
    huggingface_source_repo_name: Annotated[str, Field(
        alias="huggingface_source_repo_name",
        description="Name of the Hugging Face repository containing the data export to preprocess."
                    "It has to contain 'xml' and 'image' columns."
                    "If the repository is private, a Hugging Face token is required.",
        title="HuggingFace-Repo-Name",
        serialization_alias="source",
        examples=["username/repo-name"],
    )]


class PreprocessResponseModel(PreprocessBaseModel):
    request_id: Annotated[str, Field(
        default_factory=lambda: str(uuid4()),
        alias="request_id",
        description="Unique identifier for the preprocess request.",
        title="Request-ID",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )]
    source: Annotated[str, Field(
        alias="source",
        description="Source of the data to preprocess. Can be Zip-URL or Huggingface-Repo-Name.",
        title="Source",
    )]
    created_at: Annotated[datetime | None, Field(
        default_factory=lambda: datetime.now(UTC),
        alias="created_at",
        description="Timestamp of the preprocess status creation.",
        title="Created-At",
    )]
    started_at: Annotated[datetime | None, Field(
        default=None,
        alias="started_at",
        description="Timestamp of the preprocess start.",
        title="Started-At",
    )]
    ended_at: Annotated[datetime | None, Field(
        default=None,
        alias="ended_at",
        description="Timestamp of the preprocess ended.",
        title="Ended-At",
    )]
    runtime_seconds: Annotated[float, Field(
        default=0.0,
        alias="runtime",
        description="Runtime of the preprocess status in seconds.",
        title="Runtime",
    )]
    state: Annotated[StateEnum, Field(
        default=StateEnum.PENDING,
        alias="state",
        description="Current state of the preprocess status."
                    "Can be 'in_progress', 'failed', or 'done'.",
        title="State",
    )]
    retry_count: Annotated[int, Field(
        default=0,
        alias="retry_count",
        description="Number of times the celery task has started.",
        title="Retry-Count",
    )]
    error_message: Annotated[str | None, Field(
        default=None,
        alias="error_message",
        description="Error message during preprocess.",
        title="Error-Message",
    )]
    total_pages: Annotated[int, Field(
        default=0,
        alias="total_pages",
        description="Total number of pages to preprocess.",
        title="Total-Pages",
    )]
    total_regions: Annotated[int, Field(
        default=0,
        alias="total_regions",
        description="Total number of regions to preprocess.",
        title="Total-Regions",
    )]
    total_lines: Annotated[int, Field(
        default=0,
        alias="total_lines",
        description="Total number of lines to preprocess.",
        title="Total-Lines",
    )]
    average_regions_per_page: Annotated[float, Field(
        default=0.0,
        alias="average_regions_per_page",
        description="Average number of regions per page.",
        title="Average-Regions-Per-Page",
    )]
    average_lines_per_page: Annotated[float, Field(
        default=0.0,
        alias="average_lines_per_page",
        description="Average number of lines per page.",
        title="Average-Lines-Per-Page",
    )]

    @field_validator("source", mode="before")
    @classmethod
    def convert_url(cls, v: str | HttpUrl) -> str:
        """

        Args:
            v: URL or string to convert to url-string.

        Returns:
            URL as string.
        """
        if isinstance(v, HttpUrl):
            return str(v)
        else:
            return v.strip()

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )
