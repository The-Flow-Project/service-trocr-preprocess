"""
Logger configuration for the FLOW Preprocessing Service with loguru.
"""
import atexit
import sys
from pathlib import Path
from loguru import logger
from flow_preprocessing import setup_logger as flow_preprocess_setup_logger
from pagexml_hf import setup_logger as pagexml_hf_setup_logger


def setup_logger(
        level: str = "DEBUG",
        process_name: str = "app",
        log_files: bool = False,
        load_dependency_loggers: bool = False,
) -> None:
    """
    Configure the Loguru logger for the application.

    Each process (API, Celery worker) writes to its own log files to avoid
    concurrent write conflicts when running locally.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        process_name: Identifier for the process, used as log file prefix
                      (e.g. "api" or "worker").
        log_files: If True, log files will be written to log_dir.
        load_dependency_loggers: If True, load dependency loggers into memory.
    """
    # Remove default handler
    try:
        logger.remove(0)
    except ValueError:
        pass  # Default handler doesn't exist

    # Console handler with colored output
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | " \
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
        backtrace=False,
        diagnose=False,
        enqueue=True,
    )

    if log_files:
        # File handler for all logs with rotation
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)

        diagnose = level == "DEBUG"

        logger.add(
            logs_dir / f"{process_name}.log",
            rotation="5 MB",
            retention="10 days",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            backtrace=True,
            diagnose=diagnose,
            enqueue=True,  # Thread-safe logging
        )

        # Separate error log file
        logger.add(
            logs_dir / f"{process_name}.errors.log",
            rotation="5 MB",
            retention="30 days",
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            backtrace=True,
            diagnose=diagnose,
            enqueue=True,
        )

    if load_dependency_loggers:
        flow_preprocess_setup_logger(level=level, log_files=log_files)
        pagexml_hf_setup_logger(level=level, log_files=log_files)

    # Ensure the async queue is flushed before the process exits.
    atexit.register(_flush_logger)

    logger.debug(f"Logger initialized with level: {level}, process: {process_name}")


def _flush_logger() -> None:
    """Flush all enqueued log records. Called automatically via atexit."""
    logger.complete()
