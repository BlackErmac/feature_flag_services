from pydantic import BaseModel
from typing import List
from datetime import datetime

class Message(BaseModel):
    message : str

class FeatureFlagBase(BaseModel):
    name: str
    dependencies: List[str] = []

class FeatureFlagCreate(FeatureFlagBase):
    pass

class FeatureFlagUpdate(FeatureFlagBase):
    pass

class FeatureFlag(FeatureFlagBase):
    id: int
    enabled: bool
    
    class Config:
        from_attributes = True
        orm_mode = True


class FeatureFlagToggle(BaseModel):
    enabled: bool

class AuditLog(BaseModel):
    id: int
    flag_name: str
    action: str
    actor: str
    reason: str
    timestamp: datetime
    
    class Config:
        from_attributes = True
        orm_mode = True