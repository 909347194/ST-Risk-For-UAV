"""ORM 模型 — 航线规划结果表

表归属：**Python 写入**。

waypoints 用 JSONB 而非 PostGIS 线几何：领域模型 PathPlan.waypoints
是含到达时间的航点列表，转几何会丢掉时间维度。若将来需要按航线做
空间查询，再补一个由 waypoints 派生的 LINESTRING Z 列。
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base import Base


class PathPlanModel(Base):
    __tablename__ = 'path_plans'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    algorithm = Column(String, nullable=False)
    waypoints = Column(JSONB, nullable=False, default=list)
    total_distance = Column(Float, nullable=False)
    estimated_time = Column(Float, nullable=False)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
