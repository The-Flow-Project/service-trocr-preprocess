import io
import logging
import os.path
import shutil
import zipfile
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
    BackgroundTasks
)
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.responses import StreamingResponse

from app.database import mongo_database
from app.db_connection import (
    ping_mongo_db_server,
)

from app.models import PreprocessRequestModel, PreprocessResponseModel, PreprocessDBModel, PyObjectId
from app.worker import preprocess_task

logger = logging.getLogger('uvicorn')

ENCODERS_BY_TYPE[ObjectId] = str
logging.basicConfig(level=logging.INFO)


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
) -> PreprocessDBModel:
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

    return PreprocessDBModel(**preprocess_status)


async def check_password(
        password: str,
        preprocess_status: PreprocessDBModel,
) -> bool:
    """

    :param password:
    :param preprocess_status:
    :return:
    """
    if password is None and preprocess_status.password == '':
        return True
    if password is None and preprocess_status.password is not None:
        raise HTTPException(status_code=401, detail="Password required")
    if preprocess_status.password != password:
        raise HTTPException(status_code=401, detail="Invalid password")
    return True


@app.get(
    "/status/{preprocess_id}",
    response_description="Retrieve a preprocess status by ObjectID.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
)
async def get_preprocess_status(
        password: str = None,
        preprocess_status: PreprocessDBModel = Depends(get_preprocess_status_or_404)
) -> PreprocessResponseModel:
    """
    Retrieve a preprocess status by ObjectID.

    Args:
        preprocess_id (str): The ObjectID of the preprocess status to retrieve.

    Returns:
        dict: The found PreprocessStatus object.
        :param password:
        :param preprocess_status:
    """
    new_status = preprocess_status
    password_val = await check_password(password, new_status)
    if password_val:
        return PreprocessResponseModel(**new_status.model_dump(by_alias=True, exclude={"password"}))
    else:
        raise HTTPException(status_code=401, detail="Invalid password")


@app.post(
    "/preprocess",
    response_description="Start a new preprocess job.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
)
async def create_preprocess_status(
        background_tasks: BackgroundTasks,
        preprocess_parameters: PreprocessRequestModel = Body(...),
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> dict[str, str]:
    """
    Create a new preprocess status.

    Args:
        preprocess_parameters (PreprocessStatus): The preprocess status to create.
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.
        background_tasks (BackgroundTasks): The background tasks object, injected by FastAPI.

    Returns:
        PreprocessStatusInDB: The created PreprocessStatus object.
    """
    result = await db.preprocess_status.insert_one(
        preprocess_parameters.model_dump(exclude={"github_access_token"})
    )
    created_preprocess_status = await db.preprocess_status.find_one({"_id": result.inserted_id})

    if created_preprocess_status:
        created_preprocess_status = PreprocessDBModel(
            id=PyObjectId(str(created_preprocess_status["_id"])),
            **created_preprocess_status
        )

        # Start the preprocess job
        background_tasks.add_task(
            preprocess_task,
            github_access_token=preprocess_parameters.github_access_token,
            created_status=created_preprocess_status,
            db=db,
        )
        # new_status = await db.preprocess_status.find_one({"_id": result.inserted_id})
        # return PreprocessResponseModel(**new_status)
        return {
            "id": str(created_preprocess_status.id),
            "state": created_preprocess_status.state,
            "repo_name": created_preprocess_status.repo_name,
            "repo_folder": created_preprocess_status.repo_folder,
            "directory": created_preprocess_status.directory,
            "in_path": created_preprocess_status.in_path,
            "out_path": created_preprocess_status.out_path,
            "password": created_preprocess_status.password,
            "created_at": created_preprocess_status.created_at,
            "abbrev": created_preprocess_status.abbrev,
            "crop": created_preprocess_status.crop,
            "stop_on_fail": created_preprocess_status.stop_on_fail,
        }
    else:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/status",
    response_description="Retrieve all preprocess statuses.",
    response_model=list[PreprocessResponseModel],
    response_model_by_alias=False,
)
async def get_all_preprocess_statuses(
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> list:
    """
    Retrieve all preprocess statuses.

    Args:
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.

    Returns:
        list[PreprocessStatusInDB]: A list of all found PreprocessStatus objects without password.
    """
    query = {"password": {"$eq": None, "$exists": True}}
    preprocess_statuses = await db.preprocess_status.find(query).to_list(length=None)
    query2 = {"password": {"$eq": "", "$exists": True}}
    preprocess_statuses2 = await db.preprocess_status.find(query2).to_list(length=None)

    preprocess_statuses.extend(preprocess_statuses2)

    responses = [
        PreprocessResponseModel(
            id=PyObjectId(preprocess_status["_id"]),
            **preprocess_status
        ).model_dump(by_alias=True)
        for preprocess_status in preprocess_statuses
    ]
    return responses


@app.delete(
    "/status/{preprocess_id}",
    response_description="Delete a preprocess status by ObjectID.",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_preprocess_status(
        password: str = None,
        preprocess_status: PreprocessDBModel = Depends(get_preprocess_status_or_404),
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> None:
    """
    Delete a preprocess status by ObjectID.

    Args:
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.
        :param password:
        :param db:
        :param preprocess_status:
    """
    password_val = await check_password(password, preprocess_status)

    if password_val:
        folder_path_out = os.path.join(preprocess_status.directory,
                                       preprocess_status.out_path,
                                       str(preprocess_status.id)
                                       )
        folder_path_in = os.path.join(preprocess_status.directory,
                                      preprocess_status.in_path,
                                      str(preprocess_status.id)
                                      )
        if os.path.exists(folder_path_out):
            shutil.rmtree(folder_path_out)
        if os.path.exists(folder_path_in):
            shutil.rmtree(folder_path_in)

        if os.path.exists('logs'):
            for file in os.listdir('logs'):
                if file.startswith(str(preprocess_status.id)):
                    os.remove(os.path.join('logs', file))

        await db.preprocess_status.delete_one({"_id": preprocess_status.id})
    else:
        raise HTTPException(status_code=401, detail="Invalid password")


@app.get(
    "/files/{preprocess_id}",
    response_description="Retrieve all files of a preprocess job.",
)
async def get_preprocess_files(
        password: str = None,
        preprocess_status: PreprocessDBModel = Depends(get_preprocess_status_or_404),
) -> StreamingResponse:
    """
    Retrieve all files of a preprocess job.

    Args:
        preprocess_id (str): The ObjectID of the preprocess status to retrieve files for.

    Returns:
        dict: A dictionary containing the file names and their content.
        :param password:
        :param preprocess_status:
    """
    password_val = await check_password(password, preprocess_status)

    if password_val:
        folder_path_out = os.path.join(preprocess_status.directory,
                                       preprocess_status.out_path,
                                       str(preprocess_status.id)
                                       )

        if not os.path.exists(folder_path_out):
            raise HTTPException(status_code=404, detail="Files not found")

        zip_bytes_io = io.BytesIO()
        with zipfile.ZipFile(zip_bytes_io, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for root, _, files in os.walk(folder_path_out):
                for filename in files:
                    full_file_path = os.path.join(root, filename)
                    zipped.write(full_file_path, filename)

        response = StreamingResponse(
            iter([zip_bytes_io.getvalue()]),
            media_type="application/x-zip-compressed",
            headers={"Content-Disposition": f"inline;filename=preprocessed_{str(preprocess_status.id)}.zip",
                     "Content-Length": str(zip_bytes_io.getbuffer().nbytes)}
        )
        zip_bytes_io.close()
        return response
    else:
        raise HTTPException(status_code=401, detail="Invalid password")
