"""
Celery tasks for the preprocessing service.

Each task receives only JSON-serializable arguments (no Pydantic models,
no repository instances) and reconstructs everything it needs internally.
"""
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
from loguru import logger
from pydantic import SecretStr

from flow_preprocessing import ZipPreprocessor, HuggingFacePreprocessor, PreprocessorConfig

from app.celery_app import celery_app
from app.models import (
    Settings,
    SourceTypeEnum,
)

# Module-level settings (resolved once per worker process)
_settings = Settings()

# AIDEV-NOTE: max delay (s) between retries. With the Redis broker + acks_late +
# worker_prefetch_multiplier=1 the worker *reserves* a delayed retry into its only
# prefetch slot and is idle until it fires, so keep this small or the worker looks
# dead. Do NOT fall back to Celery's default_retry_delay (180s) by omitting countdown.
_RETRY_MAX_COUNTDOWN = 30


@celery_app.task(
    bind=True,
    name="app.tasks.preprocess_task",
    max_retries=3,
    time_limit=_settings.CELERY_TASK_TIME_LIMIT,
    soft_time_limit=_settings.CELERY_TASK_SOFT_TIME_LIMIT,
)
def preprocess_task(
        self,
        status_dict: dict,
        source_type: str,
        huggingface_token: str | None = None,
) -> dict | None:
    """
    Celery task that runs the actual preprocessing.

    A failure never takes the worker down: transient errors are retried a few
    times with a short backoff, and once retries are exhausted (or the error is
    fatal) the exception propagates so the ``task_failure`` signal marks the job
    ``FAILED``. The worker process keeps consuming the next task either way.

    Args:
        self: Celery task instance (for retries).
        status_dict: Serialized ``PreprocessResponseModel`` (JSON-safe dict).
        huggingface_token: HuggingFace API token (plain string or None).
        source_type: ``"zip"`` or ``"huggingface"``.
    """
    request_id = status_dict.get("request_id", "")
    logger.info(f"Celery task {request_id} started for preprocessing, source: {source_type}")
    source_type_enum = SourceTypeEnum(source_type)

    try:
        return _run_preprocessing(
            status_dict=status_dict,
            huggingface_token=huggingface_token,
            source_type=source_type_enum,
        )

    # AIDEV-NOTE: single retry strategy only. Do NOT re-add `autoretry_for=(Exception,)`
    # to the decorator — it double-retries and would also retry MaxRetriesExceededError.
    except (MemoryError, SoftTimeLimitExceeded):
        # Fatal: never retry. Propagate -> task_failure handler sets state FAILED.
        logger.exception(f"Fatal error for task {request_id}; not retrying")
        raise

    except Exception as exc:
        if "Cannot allocate memory" in str(exc):
            logger.error(f"OOM error in task {request_id}; not retrying")
            raise  # Treat as fatal -> task_failure handler sets state FAILED.
        countdown = min(2 ** self.request.retries, _RETRY_MAX_COUNTDOWN)
        logger.warning(
            f"Preprocessing failed for task {request_id} "
            f"(attempt {self.request.retries + 1}/{self.max_retries + 1}): {exc}. "
            f"Retrying in {countdown}s"
        )
        try:
            # self.retry() raises Retry (-> task_retry signal) or, once exhausted,
            # MaxRetriesExceededError, which we turn into a terminal failure below.
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            logger.exception(f"Preprocessing failed permanently for task {request_id}")
            raise


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
