from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
from app.database import get_db
from app.schemas import FlagCreate, FlagUpdate, FlagResponse, AuditLogResponse
from app.models import FeatureFlag, AuditLog
from app.redis_client import redis_cache
from app.dependencies import detect_circular_dependencies, validate_dependencies, cascade_disable
from typing import Optional

router = APIRouter(prefix="/flags", tags=["flags"])

@router.post("/", response_model=FlagResponse)
async def create_flag(flag: FlagCreate, db: AsyncSession = Depends(get_db)):
    # Check if flag already exists or not and if flag exists raise HTTPException
    flag_existence = select(FeatureFlag).where(FeatureFlag.name == flag.name)
    result = await db.execute(flag_existence)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Flag already exists")
    
    # Validate dependencies exist in database and if not raise HTTPException
    for dep in flag.dependencies:
        result = await db.execute(select(FeatureFlag).where(FeatureFlag.name == dep))
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail=f"Dependency {dep} not found")
    
    # Check for circular dependencies
    await detect_circular_dependencies(db, flag.name, flag.dependencies)
    
    # Create new flag
    new_flag : FeatureFlag = FeatureFlag(name=flag.name, dependencies=flag.dependencies)
    db.add(new_flag)
    await db.commit()
    await db.refresh(new_flag)
    
    # Cache the flag
    await redis_cache.set_flag(flag.name, {
        "id": new_flag.id,
        "name": new_flag.name,
        "is_enabled": new_flag.is_enabled,
        "dependencies": new_flag.dependencies
    })
    
    # Log creation
    audit_log = AuditLog(flag_id=new_flag.id, action="create", actor=flag.actor, reason=flag.reason)
    db.add(audit_log)
    await db.commit()
    
    return FlagResponse(**new_flag.__dict__)

@router.get("/{flag_name}", response_model=FlagResponse)
async def get_flag(flag_name: str, db: AsyncSession = Depends(get_db)):
    # Check cache first
    cached_flag = await redis_cache.get_flag(flag_name)
    if cached_flag:
        return FlagResponse(**cached_flag)

    result = await db.execute(select(FeatureFlag).where(FeatureFlag.name == flag_name))
    flag = result.scalars().first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    
    # Update cache
    await redis_cache.set_flag(flag_name, {
        "id": flag.id,
        "name": flag.name,
        "is_enabled": flag.is_enabled,
        "dependencies": flag.dependencies
    })
    
    return FlagResponse(**flag.__dict__)

@router.put("/{flag_name}", response_model=FlagResponse)
async def update_flag(flag_name: str, flag_update: FlagUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FeatureFlag).where(FeatureFlag.name == flag_name))
    flag = result.scalars().first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    
    if flag_update.dependencies is not None:
        await detect_circular_dependencies(db, flag_name, flag_update.dependencies, is_update=True)
        for dep in flag_update.dependencies:
            result = await db.execute(select(FeatureFlag).where(FeatureFlag.name == dep))
            if not result.scalars().first():
                raise HTTPException(status_code=404, detail=f"Dependency {dep} not found")
        flag.dependencies = flag_update.dependencies
    
    # If enabling flag
    if flag_update.is_enabled is not None:
        if flag_update.is_enabled:
            await validate_dependencies(db, flag_name, flag.dependencies)
        else:
            # Handle cascade disable for dependent flags
            await cascade_disable(db, flag_name, flag_update.actor, flag_update.reason or "Flag disabled")
        flag.is_enabled = flag_update.is_enabled
    
    await db.commit()
    await db.refresh(flag)
    
    # Update cache
    await redis_cache.set_flag(flag_name, {
        "id": flag.id,
        "name": flag.name,
        "is_enabled": flag.is_enabled,
        "dependencies": flag.dependencies
    })
    
    # Log update
    audit_log = AuditLog(
        flag_id=flag.id,
        action="update",
        actor=flag_update.actor,
        reason=flag_update.reason
    )
    db.add(audit_log)
    await db.commit()
    
    return FlagResponse(**flag.__dict__)

@router.delete("/{flag_name}")
async def delete_flag(flag_name: str, actor: str, reason: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FeatureFlag).where(FeatureFlag.name == flag_name))
    flag = result.scalars().first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    
    # Check if flag is a dependency for other flags
    result = await db.execute(select(FeatureFlag).where(FeatureFlag.dependencies.contains([flag_name])))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Cannot delete flag with dependent flags")
    
    # Clear cache
    await redis_cache.delete_flag(flag_name)
    
    # Log deletion
    audit_log = AuditLog(
        flag_id=flag.id,
        action="delete",
        actor=actor,
        reason=reason
    )
    db.add(audit_log)
    await db.commit()
    
    return {"message": "Flag deleted successfully"}

@router.get("/{flag_name}/audit", response_model=List[AuditLogResponse])
async def get_audit_logs(flag_name: str, db: AsyncSession = Depends(get_db)):
    stmt = select(FeatureFlag).where(FeatureFlag.name == flag_name)
    result = await db.execute(stmt)
    flag = result.scalars().first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    
    stmt = select(AuditLog).where(AuditLog.flag_id == flag.id)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [AuditLogResponse(flag_name=flag_name, **log.__dict__) for log in logs]