"""
Celery tasks for the preprocessing service.

Each task receives only JSON-serializable arguments (no Pydantic models,
no repository instances) and reconstructs everything it needs internally.
"""
from loguru import logger
from pydantic import SecretStr

from app.celery_app import celery_app
from app.models import (
    Settings,
    SourceTypeEnum,
)

from flow_preprocessing import ZipPreprocessor, HuggingFacePreprocessor, PreprocessorConfig

# Module-level settings (resolved once per worker process)
_settings = Settings()


@celery_app.task(
    bind=True,
    name="app.tasks.preprocess_task",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    time_limit=1200,
    soft_time_limit=1000,
)
def preprocess_task(
        self,
        status_dict: dict,
        source_type: str,
        huggingface_token: str | None = None,
) -> dict | None:
    """
    Celery task that runs the actual preprocessing.

    Args:
        self: Celery task instance (for retries).
        status_dict: Serialized ``PreprocessResponseModel`` (JSON-safe dict).
        huggingface_token: HuggingFace API token (plain string or None).
        source_type: ``"zip"`` or ``"huggingface"``.
    """
    logger.info(f"Celery task {status_dict.get('request_id', '')}started for preprocessing, source: {source_type}")
    source_type_enum = SourceTypeEnum(source_type)

    try:
        stats = _run_preprocessing(
            status_dict=status_dict,
            huggingface_token=huggingface_token,
            source_type=source_type_enum,
        )
        return stats

    except MemoryError:
        logger.exception("Memory error, do not retry")
        raise  # Don't retry OOM errors

    except Exception as e:
        logger.exception(f"Preprocessing failed for request: {e}")
        if "Cannot allocate memory" in str(e):
            logger.error("OOM error in task, will not retry")
            raise  # Don't retry OOM errors
        raise self.retry(exc=e)


def _run_preprocessing(
        status_dict: dict,
        source_type: SourceTypeEnum,
        huggingface_token: str | None = None,
) -> dict | None:
    """Core preprocessing logic."""
    config_fields = {
        k: status_dict.get(k, None) for k in PreprocessorConfig.model_fields
    }
    config_hf_token = None
    if "huggingface_token" in config_fields:
        config_hf_token = config_fields["huggingface_token"]
        config_fields.pop("huggingface_token")
    logger.debug(f"Preprocessor config: {config_fields}")

    huggingface_token = huggingface_token or config_hf_token
    preprocessor_config = PreprocessorConfig(
        huggingface_token=SecretStr(huggingface_token) if huggingface_token else None,
        **config_fields,
    )
    source = status_dict.get("source")
    if source_type == SourceTypeEnum.ZIP:
        preprocessor = ZipPreprocessor(
            input_path=source,
            config=preprocessor_config,
        )
    else:
        preprocessor = HuggingFacePreprocessor(
            input_path=source,
            config=preprocessor_config,
        )
    logger.info(f"Preprocessor created for {source_type.value}")
    logger.debug(f"Preprocessor config: {preprocessor.config}")
    logger.debug(f"Huggingface_token exists: {huggingface_token is not None}")
    preprocessor.preprocess()

    ##### Update status with final information and save #####
    stats = None
    if (
            hasattr(preprocessor, "converter") and
            hasattr(preprocessor.converter, "stats_cache")
    ):
        stats = preprocessor.converter.stats_cache

    return stats
