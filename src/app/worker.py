"""
This module contains the worker function that handles the preprocessing task.
"""
from datetime import datetime
import json
from pathlib import Path
import tempfile
from huggingface_hub import HfApi
from pydantic import SecretStr

from loguru import logger

from .models import PreprocessResponseModel, StateEnum, SourceTypeEnum
from .storage import StatusRepository

from flow_preprocessing import ZipPreprocessor, HuggingFacePreprocessor, PreprocessorConfig


def upload_status_to_huggingface(
        status: PreprocessResponseModel,
        huggingface_token: str | None,
) -> bool:
    """
    Upload preprocessing status as JSON to the HuggingFace dataset.

    This creates a 'preprocessing_status.json' file in the dataset repository
    so the creator can see what happened during preprocessing.

    Args:
        status: The preprocessing status to upload.
        huggingface_token: HuggingFace API token.

    Returns:
        bool: True if upload was successful, False otherwise.
    """
    try:
        api = HfApi()

        # Convert status to JSON
        status_dict = status.model_dump(by_alias=True, mode='json')
        repo_id = status_dict['huggingface_target_repo_name']

        # Use TemporaryDirectory for guaranteed cleanup (even on crashes)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "preprocessing_status.json"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(status_dict, f, ensure_ascii=False, indent=2, default=str)

            # Upload to HuggingFace
            api.upload_file(
                path_or_fileobj=str(temp_path),
                path_in_repo='preprocessing_status.json',
                repo_id=repo_id,
                repo_type='dataset',
                token=huggingface_token,
                commit_message=f"Add preprocessing status for job {status.request_id[:8]}",
            )

        logger.info(f"Successfully uploaded status to {repo_id}/preprocessing_status.json")
        return True


    except Exception as e:
        logger.error(f"Failed to upload status to HuggingFace: {e}")
        return False


def preprocess_task(
        repository: StatusRepository,
        huggingface_token: str | None,
        created_status: PreprocessResponseModel,
        source_type: SourceTypeEnum,
) -> None:
    """
    Starting the preprocessing process.

    Args:
        repository: The storage repository for saving status updates.
        huggingface_token: The Hugging Face token to authenticate with the Hugging Face API, or None if not provided.
        created_status: The status of the preprocessing when started.
        source_type: The type of the preprocessing, SourceTypeEnum (values: "zip" or "huggingface").

    Returns:
        None
    """
    logger.info(f"Preprocessing started for request {created_status.request_id}, source: {source_type}")
    logger.debug(f"Initial status: {created_status}")
    created_status_dict = created_status.model_dump(
        by_alias=True,
        include={
            "export_mode",
            "crop",
            "huggingface_target_repo_name",
            "huggingface_target_repo_private",
            "min_width_line",
            "min_height_line",
            "segment",
            "segmenter_config",
            "batch_size",
            "split_train_ratio",
            "split_seed",
            "split_shuffle",
            "allow_empty_lines",
            "augmentation_loops",
            "append",
        }
    )
    created_status_copy = created_status.model_copy(deep=True)
    logger.debug(f"Created status: {created_status_dict}")

    # Create the Preprocessor instance
    try:
        preprocessor_config = PreprocessorConfig(
            huggingface_token=SecretStr(huggingface_token) if huggingface_token else None,
            **created_status_dict
        )
        if source_type == SourceTypeEnum.ZIP:
            preprocessor = ZipPreprocessor(
                input_path=created_status_copy.source,
                config=preprocessor_config,
            )
        else:  # source_type == SourceTypeEnum.HUGGINGFACE
            preprocessor = HuggingFacePreprocessor(
                input_path=created_status_copy.source,
                config=preprocessor_config,
            )
        logger.info(f"Preprocessor created for {source_type.value}")

        # Run preprocessing
        preprocessor.preprocess()
        logger.info(f"Preprocessing completed successfully for request {created_status_copy.request_id}")

    except Exception as e:
        logger.exception(f"Preprocessing failed for request {created_status_copy.request_id}: {e}")
        created_status_copy.state = StateEnum.FAILED

        # Update status in repository
        created_status_copy.runtime_seconds = (datetime.now() - created_status_copy.created_at).total_seconds()
        repository.save(created_status_copy)
        return

    # Update status with preprocessing results
    created_status_copy.state = StateEnum.COMPLETED
    created_status_copy.runtime_seconds = (datetime.now() - created_status_copy.created_at).total_seconds()

    # Update statistics from preprocessor
    if hasattr(preprocessor.converter, 'stats_cache'):
        stats_cache = preprocessor.converter.stats_cache
        created_status_copy.total_pages = stats_cache.get("total_pages", 0)
        created_status_copy.total_regions = stats_cache.get("total_regions", 0)
        created_status_copy.total_lines = stats_cache.get("total_lines", 0)
        created_status_copy.average_regions_per_page = stats_cache.get("avg_regions_per_page", 0.0)
        created_status_copy.average_lines_per_page = stats_cache.get("avg_lines_per_page", 0.0)

    # Save final status to repository
    repository.save(created_status_copy)
    logger.info(f"Final status saved for request {created_status_copy.request_id}")

    # Upload status to HuggingFace dataset so creator can see what happened
    if created_status_copy.huggingface_target_repo_name:
        upload_success = upload_status_to_huggingface(
            status=created_status_copy,
            huggingface_token=huggingface_token,
        )
        if upload_success:
            logger.info(f"Status uploaded to HuggingFace dataset {created_status_copy.huggingface_target_repo_name}")
        else:
            logger.warning(f"Could not upload status to HuggingFace dataset")
