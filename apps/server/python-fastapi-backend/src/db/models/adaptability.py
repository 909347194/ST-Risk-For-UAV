"""ORM 模型 — 任务适配评估结果表

表归属：**Python 写入**。
"""

from sqlalchemy import Column, String, Integer, Boolean, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base import Base


class AdaptabilityResultModel(Base):
    __tablename__ = 'adaptability_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    capable = Column(Boolean, nullable=False)
    payload_ok = Column(Boolean, nullable=False)
    battery_ok = Column(Boolean, nullable=False)
    range_ok = Column(Boolean, nullable=False)
    time_ok = Column(Boolean, nullable=False)
    score = Column(Float, nullable=False)
    reasons = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
