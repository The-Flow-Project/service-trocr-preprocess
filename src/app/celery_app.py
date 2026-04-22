""" Celery application configuration for the FLOW Preprocessing Service."""
from celery import Celery
from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    before_task_publish,
    task_retry
)
from loguru import logger
from datetime import datetime, UTC, timedelta

from app.models import Settings, PreprocessResponseModel, StateEnum
from app.storage import get_redis_repository
from app.worker import upload_status_to_huggingface
from app.logging_config import setup_logger

settings = Settings()
setup_logger(settings.LOG_LEVEL, process_name="worker", log_files=settings.LOG_TO_FILES)

##### Celery instance #####
celery_app = Celery(
    "service_trocr_preprocess",
    broker=settings.REDIS_URL,
    # default: backend=None,

    include=["app.tasks"],
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    timezone="UTC",
    enable_utc=True,

    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    result_expires=timedelta(172800) if settings.is_production else timedelta(3600),  # production 48h, dev 1h
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3300,  # 55 minutes
)

redis_repository = get_redis_repository(redis_url=settings.REDIS_URL)


##### Celery signals #####

@before_task_publish.connect
def before_task_publish_handler(headers=None, body=None, **kwargs):
    """Fire before task is sent to the broker."""
    if "task" in headers:
        info = headers
        kwargs = info.get("kwargsrepr", {})
    else:
        info = body
        kwargs = info.get("kwargs", {})

    task_id = info.get("task_id")
    task_name = info.get("task")

    if redis_repository.get_by_id(task_id):
        logger.warning(f"Task {task_id} already exists")
        return
    logger.info(f"Publishing task {task_id} to broker")

    status = PreprocessResponseModel(
        request_id=task_id,
        task_name=task_name,
        state=StateEnum.PENDING,
        created_at=datetime.now(UTC),
        **kwargs,
    )
    redis_repository.save(status)


@task_prerun.connect
def task_prerun_handler(task_id=None, **kwargs):
    """Fire when task begins executing."""
    logger.info(f"Task {task_id} prerun")
    task = redis_repository.get_by_id(task_id)
    if task is None:
        logger.warning(f"Task {task_id} not found in repository during prerun")
        return
    task.state = StateEnum.IN_PROGRESS
    task.started_at = datetime.now(UTC)
    redis_repository.save(task)


@task_postrun.connect
def task_postrun_handler(task_id=None, state=None, retval=None, kwargs=None, **kw):
    """Fire when task succeeds."""
    logger.info(f"Task {task_id} postrun, state={state}")

    if state != "SUCCESS":
        return  # let task_failure handle it

    task = redis_repository.get_by_id(task_id)
    if task is None:
        logger.warning(f"Task {task_id} not found in repository during postrun")
        return
    if task.started_at:
        task.ended_at = datetime.now(UTC)
        task.runtime_seconds = (task.ended_at - task.started_at).total_seconds()

    if state == "SUCCESS":
        task.state = StateEnum.COMPLETED

        if isinstance(retval, dict):
            task.total_pages = retval.get("total_pages", 0)
            task.total_regions = retval.get("total_regions", 0)
            task.total_lines = retval.get("total_lines", 0)
            task.average_lines_per_page = retval.get("average_lines_per_page", 0.0)
            task.average_regions_per_page = retval.get("average_regions_per_page", 0.0)
    else:
        task.state = StateEnum.FAILED

    redis_repository.save(task)

    if state == "SUCCESS" and task.huggingface_target_repo_name:
        hf_token = (kwargs or {}).get("huggingface_token")
        upload_success = upload_status_to_huggingface(
            status=task,
            huggingface_token=hf_token,
        )
        if upload_success:
            logger.info(f"Task {task_id} uploaded to huggingface: {task.huggingface_target_repo_name}")
        else:
            logger.warning(f"Could not upload task {task_id} to huggingface")


@task_failure.connect
def task_failure_handler(task_id=None, exception=None, einfo=None, sender=None, **kwargs):
    """Fire when task fails."""
    logger.info(f"Task {task_id} failure")

    # IF retries remain, task_retry already handeld the state update
    if sender and sender.request.retries < sender.max_retries:
        logger.info(f"Task {task_id} will retry, skipping failure handler")
        return

    task = redis_repository.get_by_id(task_id)
    if task is None:
        logger.warning(f"Task {task_id} not found in repository during failure")
        return
    task.state = StateEnum.FAILED
    task.ended_at = datetime.now(UTC)
    task.error_message = str(exception)
    if task.started_at:
        task.runtime_seconds = (task.ended_at - task.started_at).total_seconds()
    redis_repository.save(task)


@task_retry.connect
def task_retry_handler(task_id=None, reason=None, **kwargs):
    """Fire when task fails and it retries."""
    logger.info(f"Task {task_id} retry")
    task = redis_repository.get_by_id(task_id)
    if task is None:
        logger.warning(f"Task {task_id} not found in repository during retry")
        return
    task.state = StateEnum.IN_PROGRESS
    task.retry_count += 1
    task.error_message = str(reason)
    redis_repository.save(task)
