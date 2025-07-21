from sqlalchemy import Column, Integer, String, Boolean, DateTime , ForeignKey
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
from sqlalchemy.dialects.postgresql import ARRAY

class Base(AsyncAttrs, DeclarativeBase):
    pass

class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    is_enabled = Column(Boolean, default=False)
    dependencies = Column(ARRAY(String), default=[])

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    flag_id = Column(Integer , ForeignKey("feature_flags.id"))
    action = Column(String)
    actor = Column(String)
    reason = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)