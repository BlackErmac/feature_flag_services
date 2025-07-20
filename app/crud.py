from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update , delete
from . import models, schemas
from typing import List, Optional
from collections import deque
import json
from redis.asyncio import Redis


async def create_audit_log(db : AsyncSession , audit_flag_name , action , actor , reason) -> models.AuditLog:
    audit_log = models.AuditLog(
        flag_name=audit_flag_name,
        action=action,
        actor=actor,
        reason=reason
    )
    db.add(audit_log)
    await db.commit()

    return audit_log

async def get_audit_logs(db: AsyncSession, redis: Redis) -> List[models.AuditLog]:
    cached = await redis.get("audit_logs")
    if cached:
        return [models.AuditLog(**item) for item in json.loads(cached)]
    
    result = await db.execute(select(models.AuditLog).order_by(models.AuditLog.timestamp.desc()))
    logs = result.scalars().all()
    
    await redis.setex("audit_logs", 300, json.dumps([
        {
            "id": log.id,
            "flag_name": log.flag_name,
            "action": log.action,
            "actor": log.actor,
            "reason": log.reason,
            "timestamp": log.timestamp.isoformat()
        }
        for log in logs
    ]))
    
    return logs


async def create_flag(db: AsyncSession, flag: schemas.FeatureFlagCreate, redis: Redis) -> models.FeatureFlag:
    db_flag = models.FeatureFlag(name=flag.name, dependencies=flag.dependencies)
    db.add(db_flag)
    await db.commit()
    await db.refresh(db_flag)
    
    # Log creation
    await create_audit_log(db , audit_flag_name=flag.name , action="create" , actor="system" , reason="Flag created")

    # Invalidate caches
    await redis.delete(f"flag:{flag.name}")
    await redis.delete("flags:all")
    await redis.delete("audit_logs")
    
    return db_flag


async def get_flag(db: AsyncSession, flag_name: str, redis: Optional[Redis]) -> Optional[models.FeatureFlag]:
    if redis:
        cached = await redis.get(f"flag:{flag_name}")
        if cached:
            return models.FeatureFlag(**json.loads(cached))
    
    result = await db.execute(select(models.FeatureFlag).filter_by(name=flag_name))
    flag = result.scalars().first()
    
    if flag and redis:
        await redis.setex(f"flag:{flag_name}", 60, json.dumps({
            "id": flag.id,
            "name": flag.name,
            "enabled": flag.enabled,
            "dependencies": flag.dependencies
        }))
    
    return flag

async def get_flags(db: AsyncSession, redis: Redis) -> List[models.FeatureFlag]:
    cached = await redis.get("flags:all")
    if cached:
        return [models.FeatureFlag(**item) for item in json.loads(cached)]
    
    result = await db.execute(select(models.FeatureFlag))
    flags = result.scalars().all()
    
    await redis.setex("flags:all", 300, json.dumps([{
        "id": flag.id,
        "name": flag.name,
        "enabled": flag.enabled,
        "dependencies": flag.dependencies
    } for flag in flags]))
    
    return flags

async def update_flag(db : AsyncSession , flag_name : str ,flag: schemas.FeatureFlagUpdate , redis: Redis) ->  models.FeatureFlag:
    db_flag = await get_flag(db, flag_name, redis)
    if not db_flag:
        raise ValueError("Flag not found")

    db_flag.name = flag.name
    db_flag.dependencies = flag.dependencies
    await db.commit()
    await db.refresh(db_flag)

    # Log update
    await create_audit_log(db , audit_flag_name=db_flag.name , action="update" , actor="system" , reason="Flag updated")

    # Invalidate caches
    await redis.delete(f"flag:{db_flag.name}")
    await redis.delete("flags:all")
    await redis.delete("audit_logs")

    return db_flag


async def delete_all_flags(db: AsyncSession, redis: Redis):
    await db.execute(delete(models.FeatureFlag))
    await db.commit()
    await redis.delete("flags:all")

async def detect_circular_dependency(db: AsyncSession, flag_name: str, dependencies: List[str]) -> bool:
    """Detect circular dependencies using DFS."""
    async def dfs(current: str, visited: set, path: set) -> bool:
        if current in path:
            return True
        if current in visited:
            return False
        
        visited.add(current)
        path.add(current)
        
        flag = await get_flag(db, current, None)
        if flag and flag.dependencies:
            for dep in flag.dependencies:
                if await dfs(dep, visited, path):
                    return True
        
        path.remove(current)
        return False
    
    visited = set()
    path = set()
    for dep in dependencies:
        if await dfs(dep, visited, path):
            return True
    return False


async def get_inactive_dependencies(db: AsyncSession, flag_name: str, redis: Redis) -> List[str]:
    flag = await get_flag(db, flag_name, redis)
    if not flag or not flag.dependencies:
        return []
    
    inactive_deps = []
    for dep in flag.dependencies:
        dep_flag = await get_flag(db, dep, redis)
        if not dep_flag or not dep_flag.enabled:
            inactive_deps.append(dep)
    return inactive_deps

async def toggle_flag(
    db: AsyncSession, 
    flag_name: str, 
    enabled: bool, 
    actor: str, 
    reason: str, 
    redis: Redis
) -> models.FeatureFlag:
    flag = await get_flag(db, flag_name, redis)
    if not flag:
        raise ValueError("Flag not found")
    
    await db.execute(
        update(models.FeatureFlag)
        .where(models.FeatureFlag.name == flag_name)
        .values(enabled=enabled)
    )
    print("1()()()()()()()()()()()()()()()()()()")
    await db.commit()

    
    # Re-fetch the updated flag to ensure it's persistent
    updated_flag = await get_flag(db, flag_name, redis)
    if not updated_flag:
        raise ValueError("Flag not found after update")
    
    # Log toggle
    action = "enable" if enabled else "disabled"
    await create_audit_log(db , flag_name, action , actor , reason)

    # Invalidate caches
    await redis.delete(f"flag:{flag_name}")
    await redis.delete("flags:all")
    await redis.delete("audit_logs")
    
    
    return updated_flag

async def handle_cascading_disable(db: AsyncSession, flag_name: str, actor: str, redis: Redis):
    """Disable dependent flags if a flag is disabled."""
    result = await db.execute(select(models.FeatureFlag).filter(models.FeatureFlag.dependencies.contains([flag_name])))
    dependent_flags = result.scalars().all()
    
    for dep_flag in dependent_flags:
        if dep_flag.enabled:
            await toggle_flag(db, dep_flag.name, False, actor, f"Cascading disable due to {flag_name}", redis)
            await handle_cascading_disable(db, dep_flag.name, actor, redis)

