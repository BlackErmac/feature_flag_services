from fastapi import FastAPI , HTTPException , Depends
from typing import List
from . import models, schemas , crud
from .database import engine, get_db
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI(title = "Fast api Async CRUD API")



# Create the database tables
@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


@app.post("/users/" , response_model=schemas.User)
async def create_user(
    user: schemas.UserCreate, 
    db: AsyncSession = Depends(get_db)
):
    existing_user = await crud.get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    return await crud.create_user(db, user)

@app.get("/users/", response_model=List[schemas.User])
async def read_users(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    users = await crud.get_users(db, skip=skip, limit=limit)
    return users

@app.get("/users/{user_id}", response_model=schemas.User)
async def read_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/users/{user_id}", response_model=schemas.User)
async def update_user(
    user_id: int, 
    user: schemas.UserUpdate, 
    db: AsyncSession = Depends(get_db)
):
    
    existing_user = await crud.update_user(db, user_id=user_id, user=user)
    if existing_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return existing_user


@app.delete("/users/{user_id}", response_model=schemas.Message)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    success = await crud.delete_user(db, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}