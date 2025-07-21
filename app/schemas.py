from pydantic import BaseModel
from typing import List , Optional
from datetime import datetime

class Message(BaseModel):
    message : str
        
class FlagCreate(BaseModel):
    name: str
    dependencies: List[str] = []
    actor: str
    reason: Optional[str] = None

class FlagUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    dependencies: Optional[List[str]] = None
    actor: str
    reason: Optional[str] = None

class FlagResponse(BaseModel):
    id: int
    name: str
    is_enabled: bool
    dependencies: List[str]

class AuditLogResponse(BaseModel):
    id: int
    flag_name: str
    action: str
    actor: str
    reason: Optional[str]
    timestamp: datetime