"""
Helper utilities for the preprocessing worker.

The actual Celery task lives in ``tasks.py``. This module retains
shared helper functions (e.g. HuggingFace upload) that are used by the task.
"""
import json
from pathlib import Path
import tempfile

from huggingface_hub import HfApi
from loguru import logger

from app.models import PreprocessResponseModel


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
