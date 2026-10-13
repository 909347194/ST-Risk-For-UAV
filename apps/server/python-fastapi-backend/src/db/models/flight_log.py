"""ORM 模型 — 飞行轨迹表（PostGIS 线几何 + pgvector）

表归属：**Python 写入，但当前暂无写入方**。

它表示「一次飞行会话」的聚合（轨迹线 + 特征向量 + 起止时间 + 总距离），
而现有代码只有逐点快照（flight_snapshots），尚不存在「飞行会话」这一
边界。先把表和列建好，等会话概念落地再接入写入逻辑。
"""

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
