from pydantic import BaseModel , EmailStr
from typing import Optional , List

class Message(BaseModel):
    message: str


class UserBase(BaseModel):
    email : EmailStr
    name : str

class UserCreate(UserBase):
    pass

class UserUpdate(UserBase):
    pass

class User(UserBase):
    id : int
    is_active : bool = True

    class Config:
        orm_mode = True