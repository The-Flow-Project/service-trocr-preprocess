import logging
from asyncio import gather
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorDatabase

from bson import ObjectId
from fastapi import (
    FastAPI,
    Body,
    Depends,
    HTTPException,
    status,
)
from fastapi.encoders import ENCODERS_BY_TYPE

from app.database import mongo_database
from app.db_connection import (
    ping_mongo_db_server,
)

from app.models import PreprocessStatus, PreprocessStatusInDB
from app.worker import preprocess_task

logger = logging.getLogger('uvicorn')

ENCODERS_BY_TYPE[ObjectId] = str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager for FastAPI application lifespan events.

    Args:
        app (FastAPI): The FastAPI application instance.

    Yields:
        None: This function does not yield any value but ensures database tables are created on startup.
    """
    await gather(
        ping_mongo_db_server(),
    )

    db = mongo_database()
    collection_list = await db.list_collection_names()
    if "preprocess_status" not in collection_list:
        await db.create_collection("preprocess_status")

    yield


app = FastAPI(lifespan=lifespan)


async def get_preprocess_status_or_404(
        preprocess_id: str,
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> PreprocessStatusInDB:
    """
    Retrieve a preprocess status by ObjectID or raise HTTP 404 if not found.

    Args:
        preprocess_id (str): The ObjectID of the preprocess status to retrieve.
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.

    Returns:
        dict: The found PreprocessStatus object.

    Raises:
        HTTPException: An HTTP 404 error if no PreprocessStatus object is found with the given UUID.
    """
    if not ObjectId.is_valid(preprocess_id):
        raise HTTPException(status_code=400, detail="Invalid ObjectID format")
    preprocess_status = await db.preprocess_status.find_one(
        {"_id": ObjectId(preprocess_id)}
    )

    if preprocess_status is None:
        raise HTTPException(status_code=404, detail="Preprocess status not found")

    return PreprocessStatusInDB(**preprocess_status)


@app.get(
    "/status/{preprocess_id}",
    response_description="Retrieve a preprocess status by ObjectID.",
    response_model=PreprocessStatusInDB,
    response_model_by_alias=False,
)
async def get_preprocess_status(preprocess_status: PreprocessStatusInDB = Depends(get_preprocess_status_or_404)) -> PreprocessStatusInDB:
    """
    Retrieve a preprocess status by ObjectID.

    Args:
        preprocess_id (str): The ObjectID of the preprocess status to retrieve.

    Returns:
        dict: The found PreprocessStatus object.
        :param preprocess_status:
    """
    new_status = preprocess_status
    return new_status


@app.post(
    "/preprocess",
    response_description="Start a new preprocess job.",
    response_model=PreprocessStatusInDB,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
)
async def create_preprocess_status(
        preprocess_parameters: PreprocessStatus = Body(...),
        github_access_token: str = Body(...),
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> PreprocessStatusInDB:
    """
    Create a new preprocess status.

    Args:
        preprocess_parameters (PreprocessStatus): The preprocess status to create.
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.
        github_access_token (str): The GitHub access token to use for the preprocess job.

    Returns:
        PreprocessStatusInDB: The created PreprocessStatus object.
    """
    result = await db.preprocess_status.insert_one(preprocess_parameters.model_dump(by_alias=True))
    created_preprocess_status = await db.preprocess_status.find_one({"_id": result.inserted_id})

    if created_preprocess_status:
        created_preprocess_status = PreprocessStatusInDB(**created_preprocess_status)

        # Start the preprocess job
        await preprocess_task(github_access_token, created_preprocess_status, db)
        return created_preprocess_status
    else:
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get(
    "/status",
    response_description="Retrieve all preprocess statuses.",
    response_model=list[PreprocessStatusInDB],
    response_model_by_alias=False,
)
async def get_all_preprocess_statuses(
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> list[PreprocessStatusInDB]:
    """
    Retrieve all preprocess statuses.

    Args:
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.

    Returns:
        list[PreprocessStatusInDB]: A list of all found PreprocessStatus objects.
    """
    preprocess_statuses = await db.preprocess_status.find().to_list(length=None)
    return [PreprocessStatusInDB(id=str(preprocess_status["_id"]), **preprocess_status) for preprocess_status in preprocess_statuses]
