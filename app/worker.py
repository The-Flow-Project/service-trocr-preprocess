"""
This module contains the worker function that handles the preprocessing task.
"""
from typing import Literal
from datetime import datetime
import json
import os

import aiofiles

from models import PreprocessResponseModel
from flow_preprocessor import ZipPreprocessor, HuggingFacePreprocessor


async def preprocess_task(
        huggingface_token: str,
        created_status: PreprocessResponseModel,
        source_type: Literal["zip", "huggingface"],
) -> None:
    """
    Starting the preprocessing process.

    :param huggingface_token: The Hugging Face token to authenticate with the Hugging Face API.
    :param created_status: The status of the preprocessing when started.
    :param source_type: The type of the preprocessing, either "zip" or "huggingface".
    :return: None
    """
    print("Preprocessing started")
    env_status_file = os.getenv("STATUS_FILE", "preprocessing-status.json")

    created_status_dict = created_status.model_dump(
        by_alias=True,
        include={
            "crop",
            "abbrev",
            "huggingface_new_repo_name",
            "huggingface_new_repo_private",
            "stop_on_fail",
            "min_width_line",
            "min_height_line",
            "segment",
            "segmenter_config",
            "namespace",
            "split_train_ratio",
            "split_seed",
            "split_shuffle",
            "allow_empty_lines",
        }
    )

    # Create the Preprocessor instance, dbcollector is default here
    if source_type == "zip":
        preprocessor = ZipPreprocessor(
            input_path=created_status.source,
            huggingface_token=huggingface_token,
            **created_status_dict
        )
    else:
        preprocessor = HuggingFacePreprocessor(
            input_path=created_status.source,
            huggingface_token=huggingface_token,
            **created_status_dict
        )
    print("Preprocessor created")
    try:
        await preprocessor.preprocess()
    except Exception as e:
        print(f"Preprocessing failed: {e}")
        preprocessor.state = 'failed'
        if created_status.stop_on_fail:
            raise e
    print("Preprocessing finished")

    segmenter_config = None if created_status.segmenter_config is None \
        else created_status.segmenter_config.json()

    # New entry for JSON file
    new_entry = {
        "crop": created_status.crop,
        "abbrev": created_status.abbrev,
        "huggingface_new_repo_name": created_status.huggingface_new_repo_name,
        "huggingface_new_repo_private": created_status.huggingface_new_repo_private,
        "stop_on_fail": created_status.stop_on_fail,
        "min_width_line": created_status.minwidth,
        "min_height_line": created_status.minheight,
        "segment": created_status.segment,
        "segmenter_config": segmenter_config,  # Assuming this is a JSON string
        "namespace": created_status.namespace,
        "split_train_ratio": created_status.split_train_ratio,
        "split_seed": created_status.split_seed,
        "split_shuffle": created_status.split_shuffle,
        "allow_empty_lines": created_status.allow_empty_lines,
        "request_id": created_status.request_id,
        "source": created_status.source,
        "created_at": created_status.created_at,
        "runtime_seconds": (datetime.now() - created_status.created_at).total_seconds(),
        "state": preprocessor.state,  # 'in_progress', 'completed', 'failed'
        "total_pages": preprocessor.stats["total_pages"],
        "total_regions": preprocessor.stats["total_regions"],
        "total_lines": preprocessor.stats["total_lines"],
        "average_regions_per_page": preprocessor.stats["avg_regions_per_page"],
        "average_lines_per_page": preprocessor.stats["avg_lines_per_page"],
    }

    if os.path.exists(env_status_file):
        async with aiofiles.open(env_status_file, encoding="utf-8") as f:
            try:
                content = await f.read()
                data = json.loads(content)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    data.append(new_entry)

    async with aiofiles.open(env_status_file, "w", encoding="utf-8") as f:
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        await f.write(content)
