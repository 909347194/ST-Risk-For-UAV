"""ORM 模型 — 飞行轨迹表（PostGIS 线几何 + pgvector）"""

from sqlalchemy import Column, String, Float, DateTime
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector

from src.db.base import Base


class FlightLogModel(Base):
    __tablename__ = 'flight_logs'

    id = Column(String, primary_key=True)
    uav_id = Column(String, nullable=False, index=True)
    track = Column(Geometry('LINESTRING Z', srid=4326))  # PostGIS 3D 轨迹线
    embedding = Column(Vector(128))  # pgvector 特征向量（用于轨迹相似度搜索）
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    total_distance = Column(Float)
