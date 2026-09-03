"""ORM 模型 — UAV 表（PostGIS 几何列）"""

from sqlalchemy import Column, String, Float, Enum as SAEnum
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
