import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient
from app.main import app
from app.database import get_db, engine
from app.models import Base

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    

@pytest_asyncio.fixture
async def client(setup_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest_asyncio.fixture
async def db():
    session_gen = get_db()
    session = await anext(session_gen)
    yield session
    await session.close()