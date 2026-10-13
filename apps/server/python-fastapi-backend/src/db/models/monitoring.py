"""ORM 模型 — 飞行监控表（逐点快照 + 告警）

表归属：**Python 写入**。

快照与告警分两张表：两者写入频率（高频追加 vs 低频事件）、查询方式、
保留策略都不同，合表会让快照表被两类语义污染。

ts 用浮点而非时间类型：领域模型 UAVHealthSnapshot.timestamp 是仿真
时间戳（秒），不是墙钟时间；改用 TIMESTAMPTZ 会丢掉仿真语义。
"""

from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry

from src.db.base import Base


class FlightSnapshotModel(Base):
    __tablename__ = 'flight_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    ts = Column(Float, nullable=False)
    position = Column(Geometry('POINT_Z', srid=4326), nullable=False)
    battery_remaining = Column(Float, nullable=False)
    speed = Column(Float, nullable=False)
    heading = Column(Float, nullable=False)
    is_anomaly = Column(Boolean, nullable=False, default=False)
    anomaly_reasons = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FlightAlertModel(Base):
    __tablename__ = 'flight_alerts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
