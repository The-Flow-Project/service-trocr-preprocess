"""
Main script Flow Preprocessing Service
"""
import io
import logging
import os.path
import zipfile
from asyncio import gather
from contextlib import asynccontextmanager
from typing import Union, Any
from urllib.parse import unquote

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

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

from flow_preprocessor.utils.delete_repo import deleteRepo

from database import mongo_database
from db_connection import (
    ping_mongo_db_server,
)

from models import PreprocessRequestModel, PreprocessResponseModel, PreprocessDBModel
from worker import preprocess_task, update_progress

logging.getLogger("fastapi").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)

logging.basicConfig(level=logging.WARNING)

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


app = FastAPI(title="FLOW-Preprocessing-Microservice", lifespan=lifespan)

async def get_preprocess_status_or_404(
        repo_name: str,
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> PreprocessDBModel:
    """
    Retrieve a preprocess status by the name of the GitHub repository or raise HTTP 404 if not found.

    Args:
        repo_name (str): The GitHub-repository-name of the preprocess status to retrieve.
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.

    Returns:
        dict: The found PreprocessStatus object.

    Raises:
        HTTPException: An HTTP 404 error if no PreprocessStatus object is found with the given repo_name.
    """
    if '___' in repo_name:
        repo_name = repo_name.replace('___', '/')
    else:
        repo_name = unquote(repo_name)
    if not isinstance(repo_name, str):
        raise HTTPException(status_code=400, detail="Invalid repo_name format.")
    preprocess_status = await db.preprocess_status.find_one(
        {"repo_name": repo_name},
    )

    if preprocess_status is None:
        raise HTTPException(status_code=404, detail="Preprocess status not found")

    return PreprocessDBModel(**preprocess_status)


def check_password(
        password: str,
        preprocess_status: Union[PreprocessDBModel, dict],
) -> bool:
    """

    :param password:
    :param preprocess_status:
    :return:
    """
    if type(preprocess_status) is PreprocessDBModel:
        status_password = preprocess_status.password
    else:
        status_password = preprocess_status["password"]

    if password is None and status_password == '':
        return True
    if password is None and status_password is not None:
        raise HTTPException(status_code=401, detail="Password required")
    if status_password != password:
        raise HTTPException(status_code=401, detail="Invalid password")
    return True


async def delete_preprocess_data(
        repo_name: str,
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> str:
    """
    Delete a preprocess status by the name of the GitHub repository or raise HTTP 404.

    Args:
        repo_name (str): The GitHub-repository-name of the preprocess status to delete.
        db (AsyncIOMotorDatabase): The MongoDB database connection object.

    Returns:
        bool: True if the preprocess status was deleted, False otherwise.
    """
    if '___' in repo_name:
        repo_name = repo_name.replace('___', '/')
    else:
        repo_name = unquote(repo_name)
    preprocess_status = await db.preprocess_status.find_one({"repo_name": repo_name})

    if preprocess_status:
        await db.preprocess_status.delete_one({"_id": preprocess_status["_id"]})
        response = await deleteRepo(repo_name=repo_name)
        if not response[0]:
            raise HTTPException(status_code=404, detail=response[1])

    return f"Repository {repo_name} has successfully been deleted."


@app.get(
    "/status/{repo_name:path}",
    response_description="Retrieve a preprocess status by the "
                         "GitHub repository name (replace the '/' with '___')",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
)
def get_preprocess_status(
        password: str = None,
        preprocess_status: PreprocessDBModel = Depends(get_preprocess_status_or_404),
) -> PreprocessResponseModel:
    """
    Retrieve a preprocess status by the GitHub repository name.

    Args:
        repo_name (str): The GitHub-repository-name of the preprocess status to retrieve.

    Returns:
        dict: The found PreprocessStatus object.
        :param password:
        :param preprocess_status:
    """
    new_status = preprocess_status
    password_val = check_password(password, new_status)
    if password_val:
        return PreprocessResponseModel(
            **new_status.model_dump(by_alias=True, exclude={"password"})
        )
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
) -> Any:
    """
    Create a new preprocess status.

    Args:
        preprocess_parameters (PreprocessStatus): The preprocess status to create.
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.
        background_tasks (BackgroundTasks): The background tasks object, injected by FastAPI.

    Returns:
        PreprocessStatusInDB: The created PreprocessStatus object.
    """
    preprocess_status = await db.preprocess_status.find_one({"repo_name": preprocess_parameters.repo_name})
    if preprocess_status:
        password_val = check_password(preprocess_parameters.password, preprocess_status)
        if password_val:
            updated_data = {**preprocess_status, **preprocess_parameters.model_dump(by_alias=True)}
            preprocess_status = PreprocessDBModel(**updated_data)
            await update_progress(preprocess_status, db=db, first=False)
        else:
            raise HTTPException(status_code=401, detail="Invalid password")
    else:
        await delete_preprocess_data(preprocess_parameters.repo_name, db=db)
        created = await db.preprocess_status.insert_one(
            preprocess_parameters.model_dump(exclude={"github_access_token"})
        )
        preprocess_status = await db.preprocess_status.find_one({"_id": created.inserted_id})
        preprocess_status = PreprocessDBModel(**preprocess_status)

    if preprocess_status:
        print("Calling preprocess task")
        # Start the preprocess job
        background_tasks.add_task(
            preprocess_task,
            github_access_token=preprocess_parameters.github_access_token,
            created_status=preprocess_status,
            db=db,
        )
        return {
            "id": preprocess_status.id,
            "state": preprocess_status.state,
            "repo_name": preprocess_status.repo_name,
            "repo_folder": preprocess_status.repo_folder,
            "password": preprocess_status.password,
            "created_at": preprocess_status.created_at,
            "abbrev": preprocess_status.abbrev,
            "crop": preprocess_status.crop,
            "stop_on_fail": preprocess_status.stop_on_fail,
            "status": preprocess_status.state,
            "progress": preprocess_status.progress,
            "files_total": preprocess_status.files_total,
            "files_successful": preprocess_status.files_successful,
        }
    else:
        raise HTTPException(status_code=500, detail="Internal server error - no preprocess status")


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

    if len(preprocess_statuses) == 0:
        return []

    responses = [
        PreprocessResponseModel(
            **preprocess_status
        ).model_dump(by_alias=True)
        for preprocess_status in preprocess_statuses
    ]
    return responses


@app.delete(
    "/status/{repo_name:path}",
    response_description="Delete a preprocess status by its GitHub repo name.",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_preprocess_status(
        password: str = None,
        preprocess_status: PreprocessDBModel = Depends(get_preprocess_status_or_404),
        db: AsyncIOMotorDatabase = Depends(mongo_database),
) -> None:
    """
    Delete a preprocess status by its GitHub repo name.

    Args:
        db (AsyncIOMotorDatabase): The MongoDB database connection object, injected by FastAPI.
        :param password:
        :param db:
        :param preprocess_status:
    """
    password_val = check_password(password, preprocess_status)

    if password_val:
        await delete_preprocess_data(
            preprocess_status.repo_name,
            db=db
        )
    else:
        raise HTTPException(status_code=401, detail="Invalid password")


@app.get(
    "/files/{repo_name:path}",
    response_description="Retrieve all files of a preprocess job.",
)
async def get_preprocess_files(
        password: str = None,
        preprocess_status: PreprocessDBModel = Depends(get_preprocess_status_or_404),
) -> StreamingResponse:
    """
    Retrieve all files of a preprocess job.

    Args:
        repo_name: The name of the GitHub repo whose preprocessed files will be retrieved.

    Returns:
        dict: A dictionary containing the file names and their content.
        :param password:
        :param preprocess_status:
    """
    password_val = check_password(password, preprocess_status)
    flat_repo_name = preprocess_status.repo_name.replace('/', '___')

    if password_val:
        folder_path_out = os.path.join('data', flat_repo_name, 'preprocessed')

        if not os.path.exists(folder_path_out):
            raise HTTPException(status_code=404, detail="Files not found")

        return StreamingResponse(
            zip_generator(folder_path_out),
            media_type="application/x-zip-compressed",
            headers={"Content-Disposition": f"attachment; filename=preprocessed_data_{flat_repo_name}.zip"}
        )
    else:
        raise HTTPException(status_code=401, detail="Invalid password")


def zip_generator(folder_path):
    """Generator function to create a ZIP file on-the-fly."""
    zip_bytes_io = io.BytesIO()

    with zipfile.ZipFile(zip_bytes_io, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for root, _, files in os.walk(folder_path):
            for filename in files:
                full_file_path = str(os.path.join(root, filename))
                zipped.write(full_file_path, filename)

    zip_bytes_io.seek(0)  # Move to the start so it can be read

    # Yield chunks instead of loading everything into memory
    yield from iter(lambda: zip_bytes_io.read(1024 * 64), b"")  # 64 KB chunks

    zip_bytes_io.close()  # Close after streaming is done
