"""ORM 模型 — 任务分配结果表（run + 明细两层）

表归属：**Python 写入**。

一次 /tasks/allocate 调用 = 一条 run；该次调用里的每条 uav→task 配对
= 一条 item。这样既能按 algorithm 分组横向比较各算法的指标，又能
回放具体分配方案。
"""

import uuid

from sqlalchemy import (Column, String, Integer, Float, DateTime,
                        ForeignKey, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.db.base import Base


class AllocationRunModel(Base):
    __tablename__ = 'allocation_runs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    algorithm = Column(String, nullable=False)
    params = Column(JSONB, nullable=True)
    uav_count = Column(Integer, nullable=False)
    task_count = Column(Integer, nullable=False)
    assigned_count = Column(Integer, nullable=False)
    unassigned_count = Column(Integer, nullable=False)
    unassigned_task_ids = Column(JSONB, nullable=False, default=list)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AllocationItemModel(Base):
    __tablename__ = 'allocation_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(UUID(as_uuid=True),
                    ForeignKey('allocation_runs.id', ondelete='CASCADE'),
                    nullable=False, index=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    estimated_cost = Column(Float, nullable=False)
