"""
Models for the preprocessing service.
"""
from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict
from pydantic_core import core_schema
from typing import Optional, List, Any
from enum import Enum


class StateEnum(str, Enum):
    """
    Enum class for the state of the process.
    """
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    DONE = "done"


class PyObjectId(str):
    """
    Class to represent an ObjectId as a string.
    """

    @classmethod
    def __get_pydantic_core_schema__(
            cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate),
                ])
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            ),
        )

    @classmethod
    def validate(cls, value) -> ObjectId:
        """
        To validate a Pydantic ObjectId.
        :param value:
        :return:
        """
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId")

        return ObjectId(value)


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
    id: PyObjectId = Field(
        alias="_id",
        description="Unique identifier of the preprocess status.",
        title="Preprocess-Status-ID",
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


class PreprocessDBModel(PreprocessResponseModel):
    password: str = Field(
        alias="password",
        description="Password to access the status.",
        title="Password",
        default=None,
    )
