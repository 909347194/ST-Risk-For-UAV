"""仓储工厂 —— 默认必须是内存实现"""

import pytest

from src.repositories import factory
from src.repositories.flight_log_repo import FlightLogRepository
from src.repositories.uav_repo import UAVRepository


@pytest.fixture(autouse=True)
def _clear_repo_cache():
    """lru_cache 是进程级全局态：db 用例会把 db 仓储留在缓存里，
    不清干净会泄漏给后续 test_services（那边连不上库会直接炸）。"""
    factory.get_uav_repository.cache_clear()
    factory.get_flight_log_repository.cache_clear()
    yield
    factory.get_uav_repository.cache_clear()
    factory.get_flight_log_repository.cache_clear()


def test_default_backend_is_memory():
    """无库环境下服务必须能起 —— 默认返回内存实现"""
    assert isinstance(factory.get_uav_repository(), UAVRepository)
    assert isinstance(factory.get_flight_log_repository(), FlightLogRepository)


def test_db_backend_returns_sqlalchemy_repository(monkeypatch):
    monkeypatch.setattr(factory.get_settings(), "repository_backend", "db", raising=False)
    # 上一个用例已把 memory 结果写进 lru_cache，不清缓存本用例会拿到旧结果
    factory.get_uav_repository.cache_clear()
    repo = factory.get_uav_repository()
    assert repo.__class__.__name__ == "UAVDbRepository"


def test_unknown_backend_raises_value_error():
    with pytest.raises(ValueError, match="repository_backend"):
        factory._build_uav_repo("bogus")
