import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger('uvicorn')
mongo_client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')


async def ping_mongo_db_server():
    try:
        await mongo_client.admin.command('ping')
        logger.info('MongoDB server is up and running - connection successful')
    except Exception as e:
        logger.error(f'MongoDB server is not available: {e}')
        raise e
