"""ORM 模型 — Task 表"""

from sqlalchemy import Column, String, Float
from geoalchemy2 import Geometry

from src.db.base import Base


class TaskModel(Base):
    __tablename__ = 'tasks'

    id = Column(String, primary_key=True)
    position = Column(Geometry('POINT_Z', srid=4326), nullable=False)
    priority = Column(String, nullable=False, default='medium')
    payload_weight = Column(Float, nullable=False)
    time_limit = Column(Float, nullable=True)
