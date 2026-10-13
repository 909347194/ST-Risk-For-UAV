"""ORM 模型 — UAV 表（PostGIS 几何列）

表归属：**将来由 Node 后端写入，Python 只读**。
本轮 Node 侧尚未接库，Python 的 /uavs 端点暂时承担写入；待 Node 就绪后
Python 应退化为只读，不再提供写端点。
"""

from sqlalchemy import Column, String, Float, DateTime, func
from geoalchemy2 import Geometry

from src.db.base import Base


class UAVModel(Base):
    __tablename__ = 'uavs'

    id = Column(String, primary_key=True)
    position = Column(Geometry('POINT_Z', srid=4326), nullable=False)  # PostGIS 3D 点
    speed = Column(Float, nullable=False)
    max_payload = Column(Float, nullable=False)
    battery = Column(Float, nullable=False)
    status = Column(String, nullable=False, default='idle')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
