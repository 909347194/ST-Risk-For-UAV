"""仓储工厂 —— 按 UAV_REPOSITORY_BACKEND 返回内存或数据库实现

默认 memory：保证无库环境下服务可启动、测试可跑。
本地验真库时设 UAV_REPOSITORY_BACKEND=db。
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.repositories.flight_log_repo import FlightLogRepository
from src.repositories.uav_repo import UAVRepository
from src.utils.config import get_settings


@lru_cache
def _session_factory() -> async_sessionmaker:
    """复用全局引擎的 sessionmaker，避免每次调用新建连接池"""
    from src.db.engine import AsyncSessionLocal
    return AsyncSessionLocal


def _build_uav_repo(backend: str):
    if backend == "memory":
        return UAVRepository()
    if backend == "db":
        from src.repositories.db import UAVDbRepository
        return UAVDbRepository(_session_factory())
    raise ValueError(f"未知的 repository_backend: {backend!r}（应为 'memory' 或 'db'）")


def _build_flight_log_repo(backend: str):
    if backend == "memory":
        return FlightLogRepository()
    if backend == "db":
        from src.repositories.db import FlightLogDbRepository
        return FlightLogDbRepository(_session_factory())
    raise ValueError(f"未知的 repository_backend: {backend!r}（应为 'memory' 或 'db'）")


@lru_cache
def get_uav_repository():
    return _build_uav_repo(get_settings().repository_backend)


@lru_cache
def get_flight_log_repository():
    return _build_flight_log_repo(get_settings().repository_backend)


def get_result_repository(name: str):
    """name ∈ {'allocation', 'adaptability', 'risk', 'path_plan'}

    结果表只在 db 模式下有实现；memory 模式下返回 None，
    调用方据此跳过落库（与 UAV_PERSIST_RESULTS=off 等价）。
    """
    if get_settings().repository_backend != "db":
        return None
    from src.repositories.db import (AdaptabilityDbRepository,
                                     AllocationRunDbRepository,
                                     PathPlanDbRepository,
                                     RiskRecordDbRepository)
    mapping = {
        "allocation": AllocationRunDbRepository,
        "adaptability": AdaptabilityDbRepository,
        "risk": RiskRecordDbRepository,
        "path_plan": PathPlanDbRepository,
    }
    if name not in mapping:
        raise ValueError(f"未知的结果仓储: {name!r}，可选 {sorted(mapping)}")
    return mapping[name](_session_factory())
