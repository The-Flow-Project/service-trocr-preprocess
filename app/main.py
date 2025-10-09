"""
Main script Flow Preprocessing Service
"""
# import io
import json
import logging
import os
from typing import Any, List
# import zipfile
from contextlib import asynccontextmanager
import aiofiles

from fastapi import (
    FastAPI,
    Body,
    Depends,
    HTTPException,
    status,
    Security,
    BackgroundTasks
)
# from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader

from models import (
    ZipPreprocessRequestModel,
    HuggingfacePreprocessRequestModel,
    PreprocessResponseModel
)
from worker import preprocess_task

logging.getLogger("fastapi").setLevel(logging.DEBUG)
logging.getLogger("uvicorn").setLevel(logging.WARNING)

logging.basicConfig(level=logging.DEBUG)

api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


async def check_api_key(api_key: str | None = Security(api_key_header)) -> None:
    """
    Checking the API key from the request header against the environment variable.
    :param api_key:
    """
    env_api_key = os.getenv("API_KEY")
    if env_api_key and api_key != env_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )


async def load_json(file_path: str) -> List[PreprocessResponseModel]:
    """
    Load a JSON file and return its content as a list of PreprocessResponseModel.

    Args:
        file_path (str): The path to the JSON file.
    Returns:
        List[PreprocessResponseModel]: A list of PreprocessResponseModel instances.
    """
    logging.info("Loading JSON file %s", file_path)
    if os.path.exists(file_path):
        async with aiofiles.open(file_path, encoding='utf-8') as file:
            try:
                content = await file.read()
                data = json.loads(content)
                logging.debug("Loaded JSON file content: %s", data)
                return [PreprocessResponseModel(**item) for item in data]
            except json.JSONDecodeError:
                return []
    return []


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Asynchronous context manager for FastAPI application lifespan events.

    Args:
        _: The FastAPI application instance (unused).

    Yields:
        None: This function does not yield any value atm.
    """

    yield


app = FastAPI(title="FLOW-Preprocessing-Microservice", lifespan=lifespan)


@app.post(
    "/preprocess/zip",
    response_description="Start a new preprocess job with a ZIP-URL.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_api_key)],
)
def start_zip_preprocess(
        background_tasks: BackgroundTasks,
        preprocess_parameters: ZipPreprocessRequestModel = Body(...),
) -> Any:
    """
    Start a new preprocess job with a ZIP-URL.

    Args:
        preprocess_parameters (ZipPreprocessRequestModel): The preprocess status to create.
        background_tasks (BackgroundTasks): The background tasks object, injected by FastAPI.

    Returns:
        PreprocessResponseModel: The created PreprocessStatus object.
    """
    huggingface_token = preprocess_parameters.huggingface_token
    if not isinstance(preprocess_parameters, ZipPreprocessRequestModel):
        raise HTTPException(status_code=400, detail="Invalid parameters for zip input type")

    preprocess_status = PreprocessResponseModel(
        **preprocess_parameters.model_dump(
            by_alias=True,
            exclude={"huggingface_token"}
        )
    )

    if preprocess_status:
        print("Calling preprocess task")
        # Start the preprocess job
        background_tasks.add_task(
            preprocess_task,
            huggingface_token=huggingface_token,
            created_status=preprocess_status,
            source_type='zip',
        )
        return {
            "message": "Preprocess job started",
            **preprocess_status.dict(),
        }
    else:
        raise HTTPException(status_code=500, detail="Internal server error - no preprocess status")


@app.post(
    "/preprocess/hf",
    response_description="Start a new preprocess job with a HuggingFace RawXML repository.",
    response_model=PreprocessResponseModel,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_api_key)],
)
def start_hf_preprocess(
        background_tasks: BackgroundTasks,
        preprocess_parameters: HuggingfacePreprocessRequestModel = Body(...),
) -> Any:
    """
    Start a new preprocess job with a HuggingFace repository name.

    Args:
        preprocess_parameters (HuggingfacePreprocessRequestModel): The preprocess status to create.
        background_tasks (BackgroundTasks): The background tasks object, injected by FastAPI.

    Returns:
        PreprocessResponseModel: The created PreprocessStatus object.
    """
    huggingface_token = preprocess_parameters.huggingface_token
    if not isinstance(preprocess_parameters, HuggingfacePreprocessRequestModel):
        raise HTTPException(status_code=400, detail="Invalid parameters for huggingface input type")

    preprocess_status = PreprocessResponseModel(
        **preprocess_parameters.model_dump(
            by_alias=True,
            exclude={"huggingface_token"}
        )
    )

    if preprocess_status:
        print("Calling preprocess task")
        # Start the preprocess job
        background_tasks.add_task(
            preprocess_task,
            huggingface_token=huggingface_token,
            created_status=preprocess_status,
            source_type='huggingface',
        )
        return {
            "message": "Preprocess job started",
            **preprocess_status.dict(),
        }
    raise HTTPException(status_code=500, detail="Internal server error - no preprocess status")

@app.get(
    "/status",
    response_description="Retrieve all preprocess statuses.",
    response_model=List[PreprocessResponseModel],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_api_key)],
)
async def get_all_preprocess_statuses() -> List[PreprocessResponseModel]:
    """
    Retrieve all preprocess statuses.

    Returns:
        List[PreprocessResponseModel]: A list of all preprocess statuses.
    """
    data = await load_json("preprocessing-status.json")
    return data

# @app.get(
#     "/files/{repo_name:path}",
#     response_description="Retrieve all files of a preprocess job.",
# )
# async def get_preprocess_files(
#         password: str = None,
#         preprocess_status: PreprocessDBModel = Depends(get_preprocess_status_or_404),
# ) -> StreamingResponse:
#     """
#     Retrieve all files of a preprocess job.
#
#     Args:
#         repo_name: The name of the GitHub repo whose preprocessed files will be retrieved.
#
#     Returns:
#         dict: A dictionary containing the file names and their content.
#         :param password:
#         :param preprocess_status:
#     """
#     password_val = check_password(password, preprocess_status)
#     flat_repo_name = preprocess_status.repo_name.replace('/', '___')
#
#     if password_val:
#         folder_path_out = os.path.join('data', flat_repo_name, 'preprocessed')
#
#         if not os.path.exists(folder_path_out):
#             raise HTTPException(status_code=404, detail="Files not found")
#
#         return StreamingResponse(
#             zip_generator(folder_path_out),
#             media_type="application/x-zip-compressed",
#             headers={"Content-Disposition": f"attachment; filename=preprocessed_data_{flat_repo_name}.zip"}
#         )
#     else:
#         raise HTTPException(status_code=401, detail="Invalid password")
#
#
# def zip_generator(folder_path):
#     """Generator function to create a ZIP file on-the-fly."""
#     zip_bytes_io = io.BytesIO()
#
#     with zipfile.ZipFile(zip_bytes_io, 'w', zipfile.ZIP_DEFLATED) as zipped:
#         for root, _, files in os.walk(folder_path):
#             for filename in files:
#                 full_file_path = str(os.path.join(root, filename))
#                 zipped.write(full_file_path, filename)
#
#     zip_bytes_io.seek(0)  # Move to the start so it can be read
#
#     # Yield chunks instead of loading everything into memory
#     yield from iter(lambda: zip_bytes_io.read(1024 * 64), b"")  # 64 KB chunks
#
#     zip_bytes_io.close()  # Close after streaming is done
