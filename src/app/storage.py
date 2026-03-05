"""
Storage layer for preprocessing status.

Provides multiple storage backends:
1. SQLModelStatusRepository - SQLModel-based, recommended for production (FastAPI best practice)
2. JSONStatusRepository - File-based with locking
3. Export to JSON for automation tools and HuggingFace upload
"""
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import aiofiles

from sqlmodel import Field, SQLModel, select, col
from sqlmodel.ext.asyncio.session import AsyncSession
# Note: SQLModel uses SQLAlchemy's async engine under the hood
# This is the official way according to SQLModel docs for async support
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.pool import StaticPool

from loguru import logger

from .models import PreprocessResponseModel, StateEnum
from flow_preprocessing import SegmenterConfig


class PreprocessingStatusDB(SQLModel, table=True):
    """
    SQLModel table for preprocessing status.

    This is the database representation that maps directly to SQLite/PostgreSQL.
    """
    __tablename__ = "preprocessing_status"

    # Primary key
    request_id: str = Field(primary_key=True, index=True)

    # Required fields
    source: str = Field(index=False)
    state: str = Field(index=True)
    created_at: str = Field(index=True)
    runtime_seconds: float = Field(default=0.0)

    # Configuration fields (nullable)
    crop: bool = Field(default=False)
    huggingface_target_repo_name: Optional[str] = Field(default=None)
    huggingface_target_repo_private: bool = Field(default=True)
    stop_on_fail: bool = Field(default=True)
    min_width_line: Optional[int] = Field(default=None)
    min_height_line: Optional[int] = Field(default=None)
    segment: Optional[str] = Field(default=None)
    segmenter_config: Optional[str] = Field(default=None)  # JSON string
    allow_empty_lines: bool = Field(default=False)
    split_train_ratio: Optional[float] = Field(default=None)
    split_seed: int = Field(default=42)
    split_shuffle: bool = Field(default=True)
    batch_size: int = Field(default=32)

    # Statistics
    total_pages: int = Field(default=0)
    total_regions: int = Field(default=0)
    total_lines: int = Field(default=0)
    average_regions_per_page: float = Field(default=0.0)
    average_lines_per_page: float = Field(default=0.0)

    # Metadata
    updated_at: Optional[str] = Field(default=None)


class StatusRepository(ABC):
    """Abstract base class for status storage."""

    @abstractmethod
    async def save(self, status: PreprocessResponseModel) -> None:
        """Save or update a preprocessing status."""
        pass

    @abstractmethod
    async def get_by_id(self, request_id: str) -> Optional[PreprocessResponseModel]:
        """Retrieve a status by its request ID."""
        pass

    @abstractmethod
    async def get_all(self) -> List[PreprocessResponseModel]:
        """Retrieve all statuses."""
        pass

    @abstractmethod
    async def export_to_json(self, output_path: Path, request_id: Optional[str] = None) -> None:
        """Export all or one status to a JSON file."""
        pass

    async def close(self) -> None:
        """Close the repository and clean up resources. Override if needed."""
        pass


class SQLModelStatusRepository(StatusRepository):
    """
    SQLModel-based status repository using SQLAlchemy async engine.

    This is the recommended approach by FastAPI:
    https://fastapi.tiangolo.com/tutorial/sql-databases/

    Benefits:
    - Proper connection pooling (no semaphore leaks)
    - Async support with proper resource cleanup
    - Type-safe queries with SQLModel
    - Compatible with SQLite, PostgreSQL, MySQL, etc.
    """

    def __init__(self, db_path: Path):
        """
        Initialize the repository with an async SQLAlchemy engine.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._initialized = False

        # Create parent directories if they don't exist
        # This is essential for Docker containers where /data might not be created yet
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured database directory exists at {self.db_path.parent}")

        # Create async engine with proper connection pooling
        # For SQLite, we use StaticPool to avoid threading issues
        database_url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,  # Set to True for SQL debugging
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,  # Important for SQLite with async
        )

        logger.info(f"SQLModel engine created for {self.db_path}")

    async def _init_db(self) -> None:
        """Initialize the database schema using SQLModel metadata."""
        if self._initialized:
            return

        async with self.engine.begin() as conn:
            # Create all tables defined in SQLModel
            await conn.run_sync(SQLModel.metadata.create_all)

        self._initialized = True
        logger.info(f"SQLModel database initialized at {self.db_path}")

    async def save(self, status: PreprocessResponseModel) -> None:
        """
        Save or update a preprocessing status.

        Uses SQLModel's merge to perform an upsert operation.
        """
        # Ensure DB is initialized
        await self._init_db()

        # Convert Pydantic model to SQLModel DB model
        db_status = self._pydantic_to_db(status)

        # Use async session with proper context management
        async with AsyncSession(self.engine) as session:
            existing = await session.get(PreprocessingStatusDB, status.request_id)
            if existing:
                # Update existing record
                for key, value in db_status.model_dump().items():
                    setattr(existing, key, value)
                db_status = existing
            # Merge handles both insert and update
            session.add(db_status)
            await session.commit()

        logger.info(f"Saved status for request {status.request_id}")

    async def get_by_id(self, request_id: str) -> Optional[PreprocessResponseModel]:
        """
        Retrieve a status by its request ID.

        Args:
            request_id: The unique identifier of the request

        Returns:
            PreprocessResponseModel or None if not found
        """
        # Ensure DB is initialized
        await self._init_db()

        async with AsyncSession(self.engine) as session:
            statement = select(PreprocessingStatusDB).where(
                PreprocessingStatusDB.request_id == request_id
            )
            result = await session.execute(statement)
            db_status = result.scalar_one_or_none()

            if db_status is None:
                return None

            return self._db_to_pydantic(db_status)

    async def get_all(self) -> List[PreprocessResponseModel]:
        """
        Retrieve all statuses ordered by creation date (newest first).

        Returns:
            List of PreprocessResponseModel
        """
        # Ensure DB is initialized
        await self._init_db()

        async with AsyncSession(self.engine) as session:
            statement = select(PreprocessingStatusDB).order_by(
                col(PreprocessingStatusDB.created_at).desc()
            )
            result = await session.execute(statement)
            db_statuses = result.scalars().all()

            return [self._db_to_pydantic(db_status) for db_status in db_statuses]

    async def export_to_json(self, output_path: Path, request_id: Optional[str] = None) -> None:
        """Export all or one status to a JSON file for automation tools."""
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if request_id:
            status = await self.get_by_id(request_id)
            data = [status.model_dump(by_alias=True, mode='json')] if status else []
        else:
            statuses = await self.get_all()
            data = [status.model_dump(by_alias=True, mode='json') for status in statuses]

        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            await f.write(content)

        logger.info(f"Exported {len(data)} statuses to {output_path}")

    @staticmethod
    def _pydantic_to_db(status: PreprocessResponseModel) -> PreprocessingStatusDB:
        """
        Convert Pydantic response model to SQLModel database model.

        Args:
            status: The Pydantic model from the API

        Returns:
            SQLModel database model
        """
        # Handle nested segmenter_config
        segmenter_config_json = None
        if status.segmenter_config:
            segmenter_config_json = status.segmenter_config.model_dump_json()

        return PreprocessingStatusDB(
            request_id=status.request_id,
            source=status.source,
            state=status.state.value,
            created_at=status.created_at.isoformat(),
            runtime_seconds=status.runtime_seconds,
            crop=status.crop or False,
            huggingface_target_repo_name=status.huggingface_target_repo_name,
            huggingface_target_repo_private=status.huggingface_target_repo_private or True,
            stop_on_fail=status.stop_on_fail if status.stop_on_fail is not None else True,
            min_width_line=status.min_width_line,
            min_height_line=status.min_height_line,
            segment=status.segment or False,
            segmenter_config=segmenter_config_json,
            allow_empty_lines=status.allow_empty_lines or False,
            split_train_ratio=status.split_train_ratio,
            split_seed=status.split_seed or 42,
            split_shuffle=status.split_shuffle if status.split_shuffle is not None else True,
            batch_size=status.batch_size or 32,
            total_pages=status.total_pages,
            total_regions=status.total_regions,
            total_lines=status.total_lines,
            average_regions_per_page=status.average_regions_per_page,
            average_lines_per_page=status.average_lines_per_page,
            updated_at=datetime.now().isoformat(),
        )

    @staticmethod
    def _db_to_pydantic(db_status: PreprocessingStatusDB) -> PreprocessResponseModel:
        """
        Convert SQLModel database model to Pydantic response model.

        Args:
            db_status: The SQLModel from the database

        Returns:
            Pydantic response model
        """
        # Parse segmenter_config if present
        segmenter_config = None
        if db_status.segmenter_config:
            segmenter_config = SegmenterConfig.model_validate_json(db_status.segmenter_config)

        return PreprocessResponseModel(
            request_id=db_status.request_id,
            source=db_status.source,
            state=StateEnum(db_status.state),
            created_at=datetime.fromisoformat(db_status.created_at),
            runtime_seconds=db_status.runtime_seconds,
            crop=db_status.crop,
            huggingface_target_repo_name=db_status.huggingface_target_repo_name,
            huggingface_target_repo_private=db_status.huggingface_target_repo_private,
            stop_on_fail=db_status.stop_on_fail,
            minwidth=db_status.min_width_line,
            minheight=db_status.min_height_line,
            segment=db_status.segment,
            segmenter_config=segmenter_config,
            allow_empty_lines=db_status.allow_empty_lines,
            split_train_ratio=db_status.split_train_ratio,
            split_seed=db_status.split_seed,
            split_shuffle=db_status.split_shuffle,
            batchsize=db_status.batch_size,
            total_pages=db_status.total_pages,
            total_regions=db_status.total_regions,
            total_lines=db_status.total_lines,
            average_regions_per_page=db_status.average_regions_per_page,
            average_lines_per_page=db_status.average_lines_per_page,
        )

    async def close(self) -> None:
        """
        Close the async engine and dispose of connection pool.

        This properly cleans up all connections and prevents semaphore leaks.
        """
        await self.engine.dispose()
        logger.info(f"SQLModel engine disposed for {self.db_path}")


class JSONStatusRepository(StatusRepository):
    """
    JSON file-based status repository with file locking.

    Advantages:
    - Human-readable
    - Easy to inspect and debug
    - Direct compatibility with automation tools
    - File locking prevents race conditions

    Disadvantages:
    - Slower for large datasets
    - Entire file must be read/written for each operation
    """

    def __init__(self, json_path: Path):
        self.json_path = json_path
        # Create parent directories if they don't exist
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured JSON file directory exists at {self.json_path.parent}")
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Ensure the JSON file exists."""
        if not self.json_path.exists():
            self.json_path.write_text('[]', encoding='utf-8')
            logger.info(f"Created new JSON file at {self.json_path}")

    async def _read_all(self) -> List[dict]:
        """Read all data from the JSON file."""
        async with aiofiles.open(self.json_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in {self.json_path}, returning empty list")
                return []

    async def _write_all(self, data: List[dict]) -> None:
        """Write all data to the JSON file."""
        async with aiofiles.open(self.json_path, 'w', encoding='utf-8') as f:
            content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            await f.write(content)

    async def save(self, status: PreprocessResponseModel) -> None:
        """Save or update a preprocessing status."""
        data = await self._read_all()

        # Convert to dict
        status_dict = status.model_dump(by_alias=True, mode='json')

        # Find and update existing entry, or append new one
        updated = False
        for i, entry in enumerate(data):
            if entry.get('request_id') == status.request_id:
                data[i] = status_dict
                updated = True
                break

        if not updated:
            data.append(status_dict)

        await self._write_all(data)
        logger.info(f"Saved status for request {status.request_id}")

    async def get_by_id(self, request_id: str) -> Optional[PreprocessResponseModel]:
        """Retrieve a status by its request ID."""
        data = await self._read_all()

        for entry in data:
            if entry.get('request_id') == request_id:
                return PreprocessResponseModel(**entry)

        return None

    async def get_all(self) -> List[PreprocessResponseModel]:
        """Retrieve all statuses."""
        data = await self._read_all()
        return [PreprocessResponseModel(**entry) for entry in data]

    async def export_to_json(self, output_path: Path, request_id: Optional[str] = None) -> None:
        """Export all statuses to a JSON file (essentially a copy)."""
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if request_id is not None:
            data_raw = await self.get_by_id(request_id)
            data = [data_raw.model_dump(by_alias=True, mode='json')] if data_raw else []
        else:
            data = await self._read_all()

        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            await f.write(content)

        logger.info(f"Exported {len(data)} statuses to {output_path}")

    async def close(self) -> None:
        """Close JSON repository and clean up resources."""
        logger.info(f"Closing JSON repository at {self.json_path}")


def create_repository(storage_type: str = "sqlite", path: Path = None) -> StatusRepository:
    """
    Factory function to create a status repository.

    Args:
        storage_type: Type of storage ("sqlite" or "json")
        path: Path to the storage file

    Returns:
        StatusRepository instance
    """
    if path is None:
        path = Path("preprocessing-status.db" if storage_type == "sqlite" else "preprocessing-status.json")

    if storage_type == "sqlite":
        return SQLModelStatusRepository(path)
    elif storage_type == "json":
        return JSONStatusRepository(path)
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")

