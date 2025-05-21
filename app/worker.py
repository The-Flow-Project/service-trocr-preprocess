from motor.motor_asyncio import AsyncIOMotorDatabase

from models import PreprocessDBModel
from flow_preprocessor.preprocessing_logic.preprocess import Preprocessor


async def update_progress(status: PreprocessDBModel, db: AsyncIOMotorDatabase, first: False) -> None:
    """
    Update the progress of a preprocess job.

    Args:
        :param first:
        :param status: The status of the preprocess job to update.
        :param db: to connect to the MongoDB.
    """
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

    created_status_dict = created_status.model_dump(by_alias=True, exclude={"password"})

    # Create the Preprocessor instance, dbcollector is default here
    preprocessor = Preprocessor(**created_status_dict, github_access_token=github_access_token, datbase=db)
    print("Preprocessor created")
    await preprocessor.preprocess()
