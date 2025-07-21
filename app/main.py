from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from . import  database
from app.router import flags

app = FastAPI(title="Feature Flag Service")
app.include_router(flags.router)

@app.on_event("startup")
async def on_startup():
    await database.init_db()
