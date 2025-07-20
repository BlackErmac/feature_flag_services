from redis.asyncio import Redis
from fastapi import Depends
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

async def get_redis():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.close()