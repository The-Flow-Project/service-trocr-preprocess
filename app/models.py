"""
Models for the preprocessing service.
"""
from datetime import datetime

from pydantic import BaseModel, BeforeValidator, Field, ConfigDict
from typing import Annotated, Optional, List, Dict, Any
from enum import Enum

PyObjectId = Annotated[str, BeforeValidator(str)]


class StateEnum(str, Enum):
    """
    Enum class for the state of the process.
    """
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    DONE = "done"


class PreprocessBaseModel(BaseModel):
    repo_name: str = Field(
        alias="repo_name",
        description="Name of the GitHub-repository.",
        title="Repository-Name",
        examples=["your_github_name/your_repo_name"],
        frozen=True,
    )
    repo_folder: Optional[str] = Field(
        default="xml",
        alias="repo_folder",
        description="Folder in the repository the files are fetched from. Defaults to 'xml'.",
        title="Repository-Folder (optional)",
        examples=["xml", "page"],
    )
    abbrev: Optional[bool] = Field(
        default=False,
        alias="abbrev",
        description="Whether to expand abbreviations in text.",
        title="Abbreviation",
    )
    crop: Optional[bool] = Field(
        default=False,
        alias="crop",
        description="Whether to crop images to their line mask.",
        title="Crop",
    )
    stop_on_fail: Optional[bool] = Field(
        default=True,
        alias="stop_on_fail",
        description="Whether to stop processing on failure.",
        title="Stop-On-Fail",
    )
    minwidth: Optional[int] = Field(
        default=None,
        alias="min-width",
        description="Minimum width of the images.",
        title="Min-Width",
    )
    segment: Optional[bool] = Field(
        alias="segment",
        description="Whether the images have to be segmented before processing.",
        title="Segment",
        default=False
    )

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )


class PreprocessRequestModel(PreprocessBaseModel):
    password: Optional[str] = Field(
        alias="password",
        description="Password to access the status.",
        title="Password (optional)",
        default=None,
    )
    github_access_token: str = Field(
        alias="github_access_token",
        description="Access token to authenticate with the GitHub API.",
        title="GitHub-Access-Token",
        examples=["ghp_1234567890"],
        default=None,
    )


class PreprocessResponseModel(PreprocessBaseModel):
    id: Optional[PyObjectId] = Field(
        alias="_id",
        description="Unique identifier of the preprocess status.",
        title="Preprocess-Status-ID",
        default=None,
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        alias="created_at",
        description="Timestamp of the preprocess status creation.",
        title="Created-At",
    )
    runtime_seconds: int = Field(
        default=0,
        alias="runtime",
        description="Runtime of the preprocess status in seconds.",
        title="Runtime",
    )
    progress: int = Field(
        default=0,
        alias="progress",
        description="Current progress of the preprocess status.",
        title="Progress",
    )
    state: StateEnum = Field(
        default=StateEnum.IN_PROGRESS,
        alias="state",
        description="Current state of the preprocess status.",
        title="State",
    )
    files_successful: int = Field(
        default=0,
        alias="files_successful",
        description="Number of files successfully processed.",
        title="Files-Successful",
    )
    files_failed_process: int = Field(
        default=0,
        alias="files_failed_process",
        description="Number of files that failed processing.",
        title="Files-Failed-Process",
    )
    files_failed_download: int = Field(
        default=0,
        alias="files_failed_download",
        description="Number of files that failed downloading.",
        title="Files-Failed-Download",
    )
    files_total: int = Field(
        default=0,
        alias="files_total",
        description="Total number of files to process.",
        title="Files-Total",
    )
    filenames_successful: List[str] = Field(
        default=[],
        alias="filenames_successful",
        description="List of filenames successfully processed.",
        title="Filenames-Successful",
    )
    filenames_failed_process: List[str] = Field(
        default=[],
        alias="filenames_failed_process",
        description="List of filenames that failed processing.",
        title="Filenames-Failed-Process",
    )
    filenames_failed_download: List[str] = Field(
        default=[],
        alias="filenames_failed_download",
        description="List of filenames that failed downloading.",
        title="Filenames-Failed-Download",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )


class PreprocessDBModel(PreprocessResponseModel):
    password: str = Field(
        alias="password",
        description="Password to access the status.",
        title="Password",
        default=None,
    )
