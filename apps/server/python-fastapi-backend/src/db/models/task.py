"""ORM 模型 — Task 表

表归属：**将来由 Node 后端写入，Python 只读**（同 uavs）。

time_limit 采用浮点：能无损容纳整数，反之会截断；与领域模型
Task.time_limit: float | None 一致。Node 侧 Drizzle 模型写的 integer
需要对齐到浮点。
"""

from sqlalchemy import Column, String, Float, DateTime, func
from geoalchemy2 import Geometry

from src.db.base import Base


class TaskModel(Base):
    __tablename__ = 'tasks'

    id = Column(String, primary_key=True)
    position = Column(Geometry('POINTZ', srid=4326), nullable=False)
    priority = Column(String, nullable=False, default='medium')
    payload_weight = Column(Float, nullable=False)
    time_limit = Column(Float, nullable=True)
    status = Column(String, nullable=False, default='pending')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
