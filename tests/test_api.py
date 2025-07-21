import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import AsyncSessionLocal, engine
from app.models import Base
from sqlalchemy import delete

@pytest.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield TestClient(app)

@pytest.mark.asyncio
async def test_create_flag(client):
    response = client.post("/flags", json={
        "name": "test_flag",
        "actor": "test_user",
        "reason": "Initial creation"
    })
    assert response.status_code == 200
    assert response.json()["name"] == "test_flag"
    assert response.json()["is_enabled"] is False

@pytest.mark.asyncio
async def test_create_flag_with_dependencies(client):
    # Create dependency flag
    client.post("/flags", json={"name": "dep_flag", "actor": "test_user"})
    
    response = client.post("/flags", json={
        "name": "test_flag",
        "dependencies": ["dep_flag"],
        "actor": "test_user"
    })
    assert response.status_code == 200
    assert response.json()["dependencies"] == ["dep_flag"]

@pytest.mark.asyncio
async def test_circular_dependency(client):
    client.post("/flags", json={"name": "flag_a", "dependencies": ["flag_b"], "actor": "test_user"})
    response = client.post("/flags", json={"name": "flag_b", "dependencies": ["flag_a"], "actor": "test_user"})
    assert response.status_code == 400
    assert "Circular dependency detected" in response.json()["detail"]

@pytest.mark.asyncio
async def test_enable_flag_with_missing_dependency(client):
    client.post("/flags", json={"name": "dep_flag", "actor": "test_user"})
    client.post("/flags", json={"name": "test_flag", "dependencies": ["dep_flag"], "actor": "test_user"})
    
    response = client.put("/flags/test_flag", json={"is_enabled": True, "actor": "test_user"})
    assert response.status_code == 400
    assert "Missing active dependencies" in response.json()["detail"]

@pytest.mark.asyncio
async def test_cascade_disable(client):
    # Create flags
    client.post("/flags", json={"name": "dep_flag", "actor": "test_user"})
    client.post("/flags", json={"name": "test_flag", "dependencies": ["dep_flag"], "actor": "test_user"})
    
    # Enable both flags
    client.put("/flags/dep_flag", json={"is_enabled": True, "actor": "test_user"})
    client.put("/flags/test_flag", json={"is_enabled": True, "actor": "test_user"})
    
    # Disable dependency
    client.put("/flags/dep_flag", json={"is_enabled": False, "actor": "test_user"})
    
    # Check if test_flag was automatically disabled
    response = client.get("/flags/test_flag")
    assert response.status_code == 200
    assert response.json()["is_enabled"] is False
    
    # Check audit log
    response = client.get("/flags/test_flag/audit")
    assert any(log["action"] == "auto-disable" for log in response.json())

@pytest.mark.asyncio
async def test_delete_flag_with_dependents(client):
    client.post("/flags", json={"name": "dep_flag", "actor": "test_user"})
    client.post("/flags", json={"name": "test_flag", "dependencies": ["dep_flag"], "actor": "test_user"})
    
    response = client.delete("/flags/dep_flag?actor=test_user")
    assert response.status_code == 400
    assert "Cannot delete flag with dependent flags" in response.json()["detail"]