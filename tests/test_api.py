import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.main import app
from app import models, database
from redis.asyncio import Redis
import asyncio
import json

DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/feature_flags_test"
REDIS_URL = "redis://localhost:6379"

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture(scope="function")
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)
        await conn.run_sync(models.Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def redis():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    await redis.flushdb()
    yield redis
    await redis.close()

@pytest.fixture
def client(db_session, redis):
    return TestClient(app)

@pytest.mark.asyncio
async def test_create_flag(client, redis):
    response = client.post("/flags/", json={"name": "auth_v2", "dependencies": []})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "auth_v2"
    assert data["enabled"] is False
    
    # Verify cache
    cached = await redis.get(f"flag:auth_v2")
    assert cached is not None
    assert json.loads(cached)["name"] == "auth_v2"

@pytest.mark.asyncio
async def test_create_flag_with_dependencies(client, redis):
    client.post("/flags/", json={"name": "auth_v2", "dependencies": []})
    response = client.post("/flags/", json={"name": "checkout_v2", "dependencies": ["auth_v2"]})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "checkout_v2"
    assert data["dependencies"] == ["auth_v2"]
    
    # Verify cache
    cached = await redis.get(f"flag:checkout_v2")
    assert cached is not None
    assert json.loads(cached)["dependencies"] == ["auth_v2"]

@pytest.mark.asyncio
async def test_create_circular_dependency(client):
    client.post("/flags/", json={"name": "flag_a", "dependencies": ["flag_b"]})
    response = client.post("/flags/", json={"name": "flag_b", "dependencies": ["flag_a"]})
    assert response.status_code == 400
    assert "Circular dependency detected" in response.json()["detail"]

@pytest.mark.asyncio
async def test_toggle_flag_missing_dependency(client, redis):
    client.post("/flags/", json={"name": "auth_v2", "dependencies": []})
    client.post("/flags/", json={"name": "checkout_v2", "dependencies": ["auth_v2"]})
    response = client.patch("/flags/checkout_v2/toggle", json={"enabled": True})
    assert response.status_code == 400
    assert "Missing active dependencies" in response.json()["detail"]
    assert response.json()["missing_dependencies"] == ["auth_v2"]

@pytest.mark.asyncio
async def test_cascading_disable(client, redis):
    client.post("/flags/", json={"name": "auth_v2", "dependencies": []})
    client.post("/flags/", json={"name": "checkout_v2", "dependencies": ["auth_v2"]})
    client.patch("/flags/auth_v2/toggle", json={"enabled": True})
    client.patch("/flags/checkout_v2/toggle", json={"enabled": True})
    
    # Disable auth_v2, should cascade to checkout_v2
    client.patch("/flags/auth_v2/toggle", json={"enabled": False})
    
    response = client.get("/flags/checkout_v2")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    
    # Verify cache invalidation
    cached = await redis.get(f"flag:checkout_v2")
    assert cached is not None
    assert json.loads(cached)["enabled"] is False

@pytest.mark.asyncio
async def test_audit_log(client, redis):
    client.post("/flags/", json={"name": "auth_v2", "dependencies": []})
    client.patch("/flags/auth_v2/toggle", json={"enabled": True}, headers={"x-actor": "test_user"})
    
    response = client.get("/audit-logs/")
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) >= 2  # Create and toggle
    assert any(log["action"] == "create" and log["flag_name"] == "auth_v2" for log in logs)
    assert any(log["action"] == "enable" and log["actor"] == "test_user" for log in logs)
    
    # Verify cache
    cached = await redis.get("audit_logs")
    assert cached is not None
    assert len(json.loads(cached)) >= 2