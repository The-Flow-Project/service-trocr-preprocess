import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
import urllib.parse

logger = logging.getLogger('uvicorn')

username = os.getenv('MONGO_INITDB_ROOT_USERNAME')
password = os.getenv('MONGO_INITDB_ROOT_PASSWORD')
host = os.getenv('MONGO_HOST')
encoded_password = urllib.parse.quote_plus(str(password))
mongo_client = AsyncIOMotorClient(f'mongodb://{username}:{password}@{host}:27017')

async def ping_mongo_db_server():
    """
    Function to check if the mongo server is up and running.
    """
    try:
        await mongo_client.admin.command('ping')
        logger.info('MongoDB server is up and running - connection successful')
    except Exception as e:
        logger.error(f'MongoDB server is not available: {e}')
        raise e
