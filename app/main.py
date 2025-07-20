from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from . import models, schemas, crud, database, dependencies
from .redis_client import get_redis, Redis

app = FastAPI(title="Feature Flag Service")

@app.on_event("startup")
async def on_startup():
    await database.init_db()

@app.post("/flags/", response_model=schemas.FeatureFlag)
async def create_flag(
    flag: schemas.FeatureFlagCreate, 
    db: AsyncSession = Depends(database.get_db),
    redis: Redis = Depends(get_redis)
):
    existing_flag = await crud.get_flag(db, flag.name , redis)
    if existing_flag:
        raise HTTPException(status_code=400, detail=f"flag {flag.name} is already exist...")
    
    # Check for circular dependencies
    if await crud.detect_circular_dependency(db, flag.name, flag.dependencies):
        raise HTTPException(status_code=400, detail="Circular dependency detected")
    
    # Validate dependencies exist
    for dep in flag.dependencies:
        if not await crud.get_flag(db, dep, redis):
            raise HTTPException(status_code=400, detail=f"Dependency {dep} does not exist")
    
    flag = await crud.create_flag(db, flag, redis)
    return flag

@app.put("/flags/{flag_name}", response_model=schemas.FeatureFlag)
async def update_flag(
    flag_name : str,
    flag: schemas.FeatureFlagUpdate,
    db: AsyncSession = Depends(database.get_db),
    redis: Redis = Depends(get_redis)
):
    flag = await crud.update_flag(db, flag_name, flag, redis)
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag

@app.patch("/flags/{flag_name}/toggle", response_model=schemas.FeatureFlag)
async def toggle_flag(
    flag_name: str, 
    toggle: schemas.FeatureFlagToggle, 
    db: AsyncSession = Depends(database.get_db),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(dependencies.get_actor)
):
    flag = await crud.get_flag(db, flag_name, redis)
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    
    if toggle.enabled:
        # Check if dependencies are active
        missing_deps = await crud.get_inactive_dependencies(db, flag_name, redis)
        if missing_deps:
            raise HTTPException(
                status_code=400,
                detail={"error": "Missing active dependencies", "missing_dependencies": missing_deps}
            )
    
    updated_flag = await crud.toggle_flag(db, flag_name, toggle.enabled, actor, "Manual toggle", redis)
    
    # Handle cascading disable
    if not toggle.enabled:
        await crud.handle_cascading_disable(db, flag_name, actor, redis)
    
    updated_flag = await crud.get_flag(db, flag_name, redis)
    return updated_flag

@app.get("/flags/", response_model=List[schemas.FeatureFlag])
async def list_flags(db: AsyncSession = Depends(database.get_db), redis: Redis = Depends(get_redis)):
    return await crud.get_flags(db, redis)

@app.get("/flags/{flag_name}", response_model=schemas.FeatureFlag)
async def get_flag(flag_name: str, db: AsyncSession = Depends(database.get_db), redis: Redis = Depends(get_redis)):
    flag = await crud.get_flag(db, flag_name, redis)
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag

@app.delete("/flags/", response_model=schemas.Message)
async def delete_all_flags(db: AsyncSession = Depends(database.get_db), redis: Redis = Depends(get_redis)):
    await crud.delete_all_flags(db , redis)
    return schemas.Message(message=f"All Flags are deleted successfully")

@app.get("/audit-logs/", response_model=List[schemas.AuditLog])
async def get_audit_logs(db: AsyncSession = Depends(database.get_db), redis: Redis = Depends(get_redis)):
    return await crud.get_audit_logs(db, redis)

