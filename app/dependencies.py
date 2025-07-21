from collections import defaultdict
from typing import List, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.models import FeatureFlag, AuditLog
from app.redis_client import redis_cache

# recursive dfs module
async def dfs(node: str, visited: Set[str], rec_stack: Set[str], all_flags: dict):
    if node in rec_stack:
        raise HTTPException(status_code=400, detail="Circular dependency detected")
    if node in visited:
        return
    visited.add(node)
    rec_stack.add(node)
    
    flag = all_flags.get(node)
    if flag and flag["dependencies"]:
        for dep in flag["dependencies"]:
            await dfs(dep, visited, rec_stack, all_flags)
    
    rec_stack.remove(node)

async def detect_circular_dependencies(db: AsyncSession, flag_name: str, dependencies: List[str], is_update: bool = False) -> None:
    # Fetch all flags using ORM
    result = await db.execute(select(FeatureFlag.name, FeatureFlag.dependencies))
    all_flags = {flag.name: {"dependencies": flag.dependencies} for flag in result.scalars().all()}
    
    # For updates, we need to consider the new dependencies
    if is_update:
        all_flags[flag_name]["dependencies"] = dependencies
    
    # Run DFS to detect cycles
    visited = set()
    rec_stack = set()
    await dfs(flag_name, visited, rec_stack, all_flags)

async def validate_dependencies(db: AsyncSession, flag_name: str, dependencies: List[str]) -> None:
    for dep in dependencies:
        result = await db.execute(select(FeatureFlag).where(FeatureFlag.name == dep))
        flag : FeatureFlag = result.scalars().first()
        if not flag:
            raise HTTPException(status_code=404, detail=f"Dependency {dep} not found")
        if not flag.is_enabled:
            raise HTTPException(status_code=400, detail={"error": "Missing active dependencies", "missing_dependencies": [dep]})

async def cascade_disable(db: AsyncSession, flag_name: str, actor: str, reason: str):
    # Find all flags that depend on this flag using ORM
    result = await db.execute(select(FeatureFlag).where(FeatureFlag.dependencies.contains([flag_name])).where(FeatureFlag.is_enabled == True))
    dependent_flags = result.scalars().all()
    
    for flag in dependent_flags:
        flag.is_enabled = False
        await redis_cache.set_flag(flag.name, {"id": flag.id, "name": flag.name, "is_enabled": False, "dependencies": flag.dependencies})
        
        # Log the cascade disable
        audit_log = AuditLog(
            flag_id=flag.id,
            action="auto-disable",
            actor=actor,
            reason=f"Cascading disable due to {flag_name} being disabled: {reason}"
        )
        db.add(audit_log)
        
        # Recursively disable dependent flags
        await cascade_disable(db, flag.name, actor, reason)