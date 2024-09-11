from app.db_connection import mongo_client
from motor.motor_asyncio import AsyncIOMotorDatabase

database = mongo_client.process_status_db


def mongo_database() -> AsyncIOMotorDatabase:
    """
    Dependency to get the database connection.
    """
    return database
