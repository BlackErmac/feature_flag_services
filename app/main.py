from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from . import models, schemas, crud, database, dependencies
from .redis_client import get_redis, Redis
from app.router import flags

app = FastAPI(title="Feature Flag Service")
app.include_router(flags.router)

@app.on_event("startup")
async def on_startup():
    await database.init_db()
