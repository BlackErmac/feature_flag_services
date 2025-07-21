import pytest
from app.models import FeatureFlag

@pytest.mark.asyncio
async def test_create_flag(client, db):
    name = "test-flag110"
    response = await client.post("/flags/", json={
        "name": name,
        "actor": "create",
        "reason": "test"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == name
    assert data["is_enabled"] is False

@pytest.mark.asyncio
async def test_create_flag_with_dependencies(client , db):
    name = "test-flag111"
    response = await client.post("/flags/", json={
        "name": name,
        "dependencies": ["test-flag110"],
        "actor": "create",
        "reason": "test",
    })
    print(response.json())
    assert response.status_code == 200
    assert response.json()["dependencies"] == ["test-flag110"]

@pytest.mark.asyncio
async def test_circular_dependency(client):
    name_a = "flag_a"
    name_b = "flag_b"
    # Create both flags without dependencies
    await client.post("/flags/", json={"name": name_a, "actor": "test_user"})
    await client.post("/flags/", json={"name": name_b, "actor": "test_user"})
    # Update flag_a to depend on flag_b
    await client.put(f"/flags/{name_a}", json={"dependencies": [name_b], "actor": "test_user"})
    # Try to update flag_b to depend on flag_a, creating a circular dependency
    response = await client.put(f"/flags/{name_b}", json={"dependencies": [name_a], "actor": "test_user"})
    assert response.status_code == 400
    assert "Circular dependency detected" in response.json()["detail"]
    
    
@pytest.mark.asyncio
async def test_enable_flag_with_missing_dependency(client):
    await client.post("/flags/", json={"name": "dep_flag", "actor": "test_user"})
    await client.post("/flags/", json={"name": "test_flag", "dependencies": ["dep_flag"], "actor": "test_user"})
    response = await client.put("/flags/test_flag", json={"is_enabled": True, "actor": "test_user"})
    assert response.status_code == 400
    assert "Missing active dependencies" in response.json()["detail"]["error"]

@pytest.mark.asyncio
async def test_cascade_disable(client):
    await client.post("/flags/", json={"name": "dep_flag", "actor": "test_user"})
    await client.post("/flags/", json={"name": "test_flag", "dependencies": ["dep_flag"], "actor": "test_user"})
    await client.put("/flags/dep_flag", json={"is_enabled": True, "actor": "test_user"})
    await client.put("/flags/test_flag", json={"is_enabled": True, "actor": "test_user"})
    await client.put("/flags/dep_flag", json={"is_enabled": False, "actor": "test_user"})
    response = await client.get("/flags/test_flag")
    assert response.status_code == 200
    assert response.json()["is_enabled"] is False
    audit_response = await client.get("/flags/test_flag/audit")
    assert any(log["action"] == "auto-disable" for log in audit_response.json())

@pytest.mark.asyncio
async def test_delete_flag_with_dependents(client):
    await client.post("/flags/", json={"name": "dep_flag", "actor": "test_user"})
    await client.post("/flags/", json={"name": "test_flag", "dependencies": ["dep_flag"], "actor": "test_user"})
    response = await client.delete("/flags/dep_flag?actor=test_user")
    assert response.status_code == 400
    assert "Cannot delete flag with dependent flags" in response.json()["detail"]