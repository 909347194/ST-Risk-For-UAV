"""ORM 模型 — 飞行风险评估记录表

表归属：**Python 写入**。
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base import Base


class RiskRecordModel(Base):
    __tablename__ = 'risk_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    risk_level = Column(String, nullable=False)
    collision_risk = Column(Float, nullable=False)
    weather_risk = Column(Float, nullable=False)
    battery_risk = Column(Float, nullable=False)
    overall_score = Column(Float, nullable=False)
    weather_factor = Column(Float, nullable=True)
    details = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
