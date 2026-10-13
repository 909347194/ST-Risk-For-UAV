"""ORM 模型 — 统一导出

新增模型必须在此导出：alembic/env.py 通过 import src.db.models 触发
全部表注册，漏导出会让 autogenerate 生成 DROP TABLE。
"""

from src.db.models.uav import UAVModel
from src.db.models.task import TaskModel
from src.db.models.flight_log import FlightLogModel
from src.db.models.allocation import AllocationRunModel, AllocationItemModel
from src.db.models.adaptability import AdaptabilityResultModel
from src.db.models.risk_record import RiskRecordModel
from src.db.models.path_plan import PathPlanModel
from src.db.models.monitoring import FlightSnapshotModel, FlightAlertModel

__all__ = [
    "UAVModel",
    "TaskModel",
    "FlightLogModel",
    "AllocationRunModel",
    "AllocationItemModel",
    "AdaptabilityResultModel",
    "RiskRecordModel",
    "PathPlanModel",
    "FlightSnapshotModel",
    "FlightAlertModel",
]
