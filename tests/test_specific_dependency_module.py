import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models import FeatureFlag
from app.dependencies import (
    detect_circular_dependencies,
    validate_dependencies,
    cascade_disable,
)

@pytest.mark.asyncio
async def test_detect_circular_dependencies(session: AsyncSession):
    # Create flags with circular dependency
    flag_a = FeatureFlag(name="A", dependencies=["B"], is_enabled=True)
    flag_b = FeatureFlag(name="B", dependencies=["A"], is_enabled=True)

    session.add_all([flag_a, flag_b])
    await session.commit()

    all_deps = ["B"]

    with pytest.raises(HTTPException) as exc:
        await detect_circular_dependencies(session, "A", all_deps)

    assert exc.value.status_code == 400
    assert "Circular dependency" in str(exc.value.detail)

@pytest.mark.asyncio
async def test_validate_dependencies(session: AsyncSession):
    # Create a dependency that is disabled
    dep = FeatureFlag(name="Dep", dependencies=[], is_enabled=False)
    session.add(dep)
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await validate_dependencies(session, "TestFlag", ["Dep"])

    assert exc.value.status_code == 400
    assert "missing_dependencies" in str(exc.value.detail)

@pytest.mark.asyncio
async def test_cascade_disable(session: AsyncSession):
    # Create flags where B depends on A, C depends on B
    flag_a = FeatureFlag(name="A", dependencies=[], is_enabled=True)
    flag_b = FeatureFlag(name="B", dependencies=["A"], is_enabled=True)
    flag_c = FeatureFlag(name="C", dependencies=["B"], is_enabled=True)

    session.add_all([flag_a, flag_b, flag_c])
    await session.commit()

    await cascade_disable(session, "A", actor="test-user", reason="test reason")
    await session.commit()

    # Refresh and assert they are disabled
    for name in ["B", "C"]:
        flag = await session.get(FeatureFlag, name)
        assert flag.is_enabled is False
