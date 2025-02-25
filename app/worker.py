from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import PreprocessDBModel, PyObjectId
from flow_preprocessor.preprocessing_logic.preprocess import Preprocessor


async def update_progress(status: PreprocessDBModel, db: AsyncIOMotorDatabase, first: False) -> None:
    """
    Update the progress of a preprocess job.

    Args:
        :param first:
        :param status: The status of the preprocess job to update.
        :param db: to connect to the MongoDB.
    """
    if isinstance(status.id, str):
        status.id = PyObjectId(status.id)

    if first:
        status_dict = status.model_dump(by_alias=True)
    else:
        status_dict = status.model_dump(by_alias=True, exclude_unset=True, exclude_defaults=True)

    del status_dict["_id"]

    await db.preprocess_status.update_one(
        {"_id": status.id},
        {"$set": status_dict},
    )


async def preprocess_task(
        github_access_token: str,
        created_status: PreprocessDBModel,
        db: AsyncIOMotorDatabase,
) -> None:
    """
    Starting the preprocessing process.

    :param github_access_token: The GitHub access token.
    :param created_status: The status of the preprocessing when started.
    :param db: to connect to the MongoDB.
    """
    print("Preprocessing started")
    await update_progress(created_status, db, first=True)

    async def callback(progress_update_status: dict) -> None:
        """
        Callback method for the preprocessing process to update the progress status.

        :param progress_update_status:
        """
        progress_update_status["_id"] = progress_update_status["process_id"]
        del progress_update_status["process_id"]
        status_in_db = PreprocessDBModel(**progress_update_status)
        try:
            await update_progress(status_in_db, db, first=False)
        except Exception as e:
            print(f"Failed to update preprocess status: {e}")

    created_status_dict = created_status.model_dump(by_alias=True, exclude={"password"})
    created_status_dict["process_id"] = str(created_status_dict["_id"])
    del created_status_dict["_id"]

    preprocessor = Preprocessor(
        **created_status_dict,
        github_access_token=github_access_token,
        callback_preprocess=callback,
    )
    print("Preprocessor created")
    await preprocessor.preprocess()
