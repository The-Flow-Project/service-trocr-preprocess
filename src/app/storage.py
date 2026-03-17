"""
Storage layer for preprocessing status.

Provides a synchronous JSON-based storage backend:
1. StatusRepository - Dictionary-based with sync JSON persistence
"""
import json
from pathlib import Path
import threading

from loguru import logger

from .models import PreprocessResponseModel


class StatusRepository:
    """
    Synchronous status repository using a dictionary and JSON file.
    """

    def __init__(self, json_path: Path):
        """
        Initialize the repository.

        Args:
            json_path: Path to the JSON file for persistence
        """
        self._lock = threading.Lock()
        self.json_path = json_path
        self._data: dict[str, PreprocessResponseModel] = {}

        # Create parent directories if they don't exist
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._load()
        logger.info(f"Initialized StatusRepository with {len(self._data)} records from {self.json_path}")

    def _load(self) -> None:
        """Load data from the JSON file into memory."""
        if not self.json_path.exists():
            self._save_to_file()
            return

        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    self._data = {}
                    return

                data_list = json.loads(content)
                self._data = {}
                for item in data_list:
                    # Convert to Pydantic model
                    model = PreprocessResponseModel(**item)
                    self._data[model.request_id] = model
        except Exception as e:
            logger.error(f"Failed to load status data from {self.json_path}: {e}")
            self._data = {}

    def _save_to_file(self) -> None:
        """Write current memory state to the JSON file."""
        try:
            # Convert all models to dicts
            data_list = [
                status.model_dump(by_alias=True, mode='json')
                for status in self._data.values()
            ]

            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data_list, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save status data to {self.json_path}: {e}")

    def save(self, status: PreprocessResponseModel) -> None:
        """
        Save or update a preprocessing status synchronously.
        Updates memory and persists to file.
        """
        with self._lock:
            self._data[status.request_id] = status
            self._save_to_file()
            logger.info(f"Saved status for request {status.request_id}")

    def get_by_id(self, request_id: str) -> PreprocessResponseModel | None:
        """
        Retrieve a status by its request ID synchronously.

        Args:
            request_id: The unique identifier of the request

        Returns:
            PreprocessResponseModel or None if not found
        """
        with self._lock:
            return self._data.get(request_id)

    def get_all(self) -> list[PreprocessResponseModel]:
        """
        Retrieve all statuses ordered by creation date (newest first).

        Returns:
            List of PreprocessResponseModel
        """
        # Sort values by created_at descending
        with self._lock:
            return sorted(
                list(self._data.values()),
                key=lambda x: x.created_at,
                reverse=True
            )

    def flush(self) -> None:
        """
        Persist current in-memory state to disk (thread-safe).
        Intended for use during shutdown or explicit save points.
        """
        with self._lock:
            self._save_to_file()
            logger.info(f"Flushed {len(self._data)} statuses to {self.json_path}")

    def export_to_json(self, output_path: Path, request_id: str | None = None) -> None:
        """Export all or one status to a JSON file for automation tools."""
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            if request_id:
                status = self._data.get(request_id)
                data = [status.model_dump(by_alias=True, mode='json')] if status else []
            else:
                statuses = sorted(
                    list(self._data.values()),
                    key=lambda x: x.created_at,
                    reverse=True,
                )
                data = [status.model_dump(by_alias=True, mode='json') for status in statuses]

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"Exported {len(data)} statuses to {output_path}")

    def close(self) -> None:
        """No-op for file based storage, but kept for interface compatibility if needed."""
        pass


def create_repository(path: Path | None = None) -> StatusRepository:
    """
    Factory function to create a status repository.

    Args:
        path: Path to the storage file

    Returns:
        StatusRepository instance
    """
    if path is None:
        path = Path("preprocessing-status.json")

    return StatusRepository(path)
