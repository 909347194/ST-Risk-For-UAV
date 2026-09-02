"""领域枚举"""

from enum import Enum


class UAVStatus(str, Enum):
    """无人机状态"""
    IDLE = "idle"
    ASSIGNED = "assigned"
    IN_FLIGHT = "in_flight"
    RETURNING = "returning"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class TaskPriority(str, Enum):
    """任务优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
