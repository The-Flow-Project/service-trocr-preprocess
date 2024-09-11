from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import PreprocessStatus, PreprocessStatusInDB
from flow_preprocessor.preprocessing_logic.preprocess import Preprocessor


async def update_progress(status: PreprocessStatusInDB, db: AsyncIOMotorDatabase) -> None:
    """
    Update the progress of a preprocess job.

    Args:
        :param status: The status of the preprocess job to update.
        :param db: to connect to the MongoDB.
    """
    if isinstance(status.id, str):
        status.id = ObjectId(status.id)

    status_dict = status.model_dump(by_alias=True)
    del status_dict["_id"]

    await db.preprocess_status.update_one(
        {"_id": status.id},
        {"$set": status_dict},
    )


async def preprocess_task(
        github_access_token: str,
        created_status: PreprocessStatus,
        db: AsyncIOMotorDatabase
) -> None:
    preprocessor = Preprocessor()

    async def callback(progress_update_status: dict) -> None:
        progress_update_status["_id"] = progress_update_status["process_id"]
        del progress_update_status["process_id"]
        status_in_db = PreprocessStatusInDB(**progress_update_status)
        try:
            await update_progress(status_in_db, db)
        except Exception as e:
            print(f"Failed to update preprocess status: {e}")

    created_status_dict = created_status.model_dump(by_alias=True)
    created_status_dict["process_id"] = str(created_status_dict["_id"])
    del created_status_dict["_id"]

    await preprocessor.preprocess(
        **created_status_dict,
        github_access_token=github_access_token,
        callback_preprocess=callback,
    )
