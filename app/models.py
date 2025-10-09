"""
Models for the preprocessing service.
"""
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict
from uuid import uuid4

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    PositiveInt,
    HttpUrl,
    field_validator,
)


class StateEnum(str, Enum):
    """
    Enum class for the state of the process.
    """
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    DONE = "completed"


class SegmenterConfig(BaseModel):
    """
    Configuration for the segmenter.
    """
    model_name: Annotated[str | None, Field(
        default=None,
        alias="model_name",
        description="Name of the Hugging Face Yolo model to use for segmentation.",
        title="Yolo Model-Name",
        examples=["Riksarkivet/yolov9-lines-within-regions-1"],
    )]
    baselines: Annotated[bool, Field(
        default=False,
        alias="baselines",
        description="Whether to create baselines.",
        title="Baselines",
    )]
    creator: Annotated[str | None, Field(
        default=None,
        alias="creator",
        description="Name of the creator to use in the metadata.",
        title="Creator",
        examples=["John Doe"],
    )]
    yolo_args: Annotated[Dict[str, Any] | None, Field(
        default=None,
        alias="yolo_args",
        description="Additional arguments for the Yolo model."
                    "See https://docs.ultralytics.com/modes/predict/#inference-arguments for details.",
        title="Yolo-Args",
        examples=[{"conf": 0.25, "iou": 0.45}],
    )]

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )


class PreprocessBaseModel(BaseModel):
    """
    Base model for preprocess requests (zip and huggingface) and responses.
    Common fields for both requests and responses.
    1. Optional fields that are commonly used.
    2. Expert mode fields that are less commonly used.
    """
    # Optional
    crop: Annotated[bool | None, Field(
        default=False,
        alias="crop",
        description="Whether to crop images to their line mask.",
        title="Crop",
    )]
    abbrev: Annotated[bool | None, Field(
        default=False,
        alias="abbrev",
        description="Whether to expand in XML available abbreviations."
                    "Default is False.",
        title="Abbrev",
    )]
    huggingface_new_repo_name: Annotated[str | None, Field(
        default=None,
        alias="huggingface_new_repo_name",
        description="Name of the new Hugging Face repository to create."
                    "If not provided, there will be no upload to Hugging Face."
                    "If provided and the repository already exists, it will be updated."
                    "If provided, a Hugging Face token is required.",
        title="HuggingFace-New-Repo-Name",
        examples=["my-new-dataset-repo"],
    )]
    huggingface_new_repo_private: Annotated[bool | None, Field(
        default=True,
        alias="huggingface_new_repo_private",
        description="Whether the new Hugging Face repository should be private."
                    "Default is True.",
        title="HuggingFace-New-Repo-Private",
    )]

    # Expert Mode Options
    segment: Annotated[bool | None, Field(
        default=False,
        alias="segment",
        description="Whether the images have to be segmented before processing.",
        title="Segment",
    )]
    segmenter_config: Annotated[SegmenterConfig | None, Field(
        default=None,
        alias="segmenter_config",
        description="Configuration for the segmenter. Required if 'segment' is True.",
        title="Segmenter-Config",
    )]
    stop_on_fail: Annotated[bool | None, Field(
        default=True,
        alias="stop_on_fail",
        description="Whether to stop processing on failure.",
        title="Stop-On-Fail",
    )]
    minwidth: Annotated[PositiveInt | None, Field(
        default=None,
        alias="min_width_line",
        description="Minimum width of the images. Images smaller than this will be skipped.",
        title="Min-Width",
    )]
    minheight: Annotated[PositiveInt | None, Field(
        default=None,
        alias="min_height_line",
        description="Minimum height of the images. Images smaller than this will be skipped.",
        title="Min-Height",
    )]
    allow_empty_lines: Annotated[bool | None, Field(
        default=False,
        alias="allow_empty_lines",
        description="Whether to allow lines without text. Default is False.",
        title="Allow-Empty-Lines",
    )]
    split_train_ratio: Annotated[float | None, Field(
        default=None,
        alias="split_train_ratio",
        description="Ratio of the training set when splitting the dataset into train, validation, and test sets."
                    "If not provided, no splitting will be done."
                    "Value must be between 0 and 1.",
        title="Split-Train-Ratio",
        examples=[0.8],
        gt=0.0,
        lt=1.0,
    )]
    split_seed: Annotated[int | None, Field(
        default=42,
        alias="split_seed",
        description="Random seed to use for splitting the dataset into train, validation, and test sets."
                    "Default is 42.",
        title="Split-Seed",
        examples=[1234],
    )]
    split_shuffle: Annotated[bool | None, Field(
        default=True,
        alias="split_shuffle",
        description="Whether to shuffle the dataset before splitting into train, validation, and test sets."
                    "Default is True.",
        title="Split-Shuffle",
    )]
    namespace: Annotated[str | None, Field(
        default=None,
        alias="namespace",
        description="XML namespace to use for the PageXML files."
                    "Default is 'http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15'.",
        title="Namespace",
        examples=["http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"],
    )]

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )


class PreprocessRequestModel(PreprocessBaseModel):
    huggingface_token: Annotated[str | None, Field(
        default=None,
        alias="huggingface_token",
        description="Hugging Face token to authenticate with the Hugging Face API."
                    "Required if 'huggingface_new_repo_name' is provided.",
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
    huggingface_repo_name: Annotated[str, Field(
        alias="huggingface_repo_name",
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
    created_at: Annotated[datetime, Field(
        default_factory=datetime.now,
        alias="created_at",
        description="Timestamp of the preprocess status creation.",
        title="Created-At",
    )]
    runtime_seconds: Annotated[float, Field(
        default=0.0,
        alias="runtime",
        description="Runtime of the preprocess status in seconds.",
        title="Runtime",
    )]
    state: Annotated[StateEnum, Field(
        default=StateEnum.IN_PROGRESS,
        alias="state",
        description="Current state of the preprocess status."
                    "Can be 'in_progress', 'failed', or 'done'.",
        title="State",
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
    def convert_url(cls, v: str | HttpUrl) -> str:
        return str(v)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )
