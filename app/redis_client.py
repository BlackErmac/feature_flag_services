import redis.asyncio as redis
import json
from typing import Optional
import os

class RedisCache:
    def __init__(self):
        self.client = redis.from_url(os.getenv("REDIS_URL"))

    async def get_flag(self, name: str) -> Optional[dict]:
        data = await self.client.get(f"flag:{name}")
        return json.loads(data) if data else None

    async def set_flag(self, name: str, data: dict):
        await self.client.set(f"flag:{name}", json.dumps(data))

    async def delete_flag(self, name: str):
        await self.client.delete(f"flag:{name}")

redis_cache = RedisCache()