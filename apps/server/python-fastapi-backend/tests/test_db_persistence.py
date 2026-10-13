"""持久化集成测试 —— 需要真实 PostgreSQL（PostGIS + pgvector）

默认被 pyproject 的 addopts 跳过。显式运行：
    pytest tests/test_db_persistence.py -q -m integration
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import UAVModel
from src.domain.enums import RiskLevel, UAVStatus
from src.domain.models import (AdaptabilityResult, Position, RiskAssessment,
                               TaskAllocation, UAV)
from src.repositories.db import (AdaptabilityDbRepository, AllocationRunDbRepository,
                                 FlightLogDbRepository, RiskRecordDbRepository,
                                 UAVDbRepository)
from src.utils.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
async def session_factory():
    engine = create_async_engine(get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def clean_uavs(session_factory):
    """用例前后各清一次 uavs 表，避免相互污染"""
    from sqlalchemy import delete
    async with session_factory() as s:
        await s.execute(delete(UAVModel))
        await s.commit()
    yield
    async with session_factory() as s:
        await s.execute(delete(UAVModel))
        await s.commit()


async def test_uav_roundtrip_keeps_z(session_factory, clean_uavs):
    """PostGIS POINT_Z 往返后 z 分量不能丢"""
    repo = UAVDbRepository(session_factory)
    uav = UAV(id="uav-z", position=Position(x=1.0, y=2.0, z=42.0),
              speed=10.0, max_payload=5.0, battery=900.0,
              status=UAVStatus.IN_FLIGHT)
    await repo.save(uav)

    got = await repo.find_by_id("uav-z")
    assert got is not None
    assert got.position.z == 42.0
    assert got.position.x == 1.0
    assert got.status == UAVStatus.IN_FLIGHT


async def test_uav_find_by_status_and_delete(session_factory, clean_uavs):
    repo = UAVDbRepository(session_factory)
    await repo.save(UAV(id="u1", position=Position(x=0, y=0, z=0), speed=1.0,
                        max_payload=1.0, battery=10.0, status=UAVStatus.IDLE))
    await repo.save(UAV(id="u2", position=Position(x=0, y=0, z=0), speed=1.0,
                        max_payload=1.0, battery=10.0, status=UAVStatus.MAINTENANCE))

    assert [u.id for u in await repo.find_by_status(UAVStatus.MAINTENANCE)] == ["u2"]
    assert await repo.delete("u1") is True
    assert await repo.find_by_id("u1") is None


async def test_allocation_run_saves_items_matching_assigned_count(session_factory):
    """assigned_count 必须与实际写入的 items 行数一致"""
    repo = AllocationRunDbRepository(session_factory)
    run_id = await repo.save_run(
        algorithm="hungarian",
        params={"foo": 1},
        uav_count=2,
        task_count=3,
        allocations=[TaskAllocation(uav_id="u1", task_id="t1", estimated_cost=1.5),
                     TaskAllocation(uav_id="u2", task_id="t2", estimated_cost=2.5)],
        unassigned_task_ids=["t3"],
        duration_ms=12.0,
    )

    detail = await repo.get_run(run_id)
    assert detail is not None
    assert detail["assigned_count"] == 2
    assert len(detail["allocations"]) == 2
    assert detail["unassigned_task_ids"] == ["t3"]
    assert detail["params"] == {"foo": 1}


async def test_allocation_run_not_found_returns_none(session_factory):
    repo = AllocationRunDbRepository(session_factory)
    assert await repo.get_run(uuid.uuid4()) is None


async def test_risk_record_roundtrip_keeps_details(session_factory):
    repo = RiskRecordDbRepository(session_factory)
    assessment = RiskAssessment(uav_id="u-risk", task_id="t-risk",
                                risk_level=RiskLevel.CRITICAL,
                                collision_risk=0.9, weather_risk=0.8,
                                battery_risk=0.2, overall_score=0.85,
                                details=["高风险"])
    await repo.save(assessment, weather_factor=0.7)

    rows = await repo.find_by_uav("u-risk")
    assert len(rows) >= 1
    assert rows[0]["risk_level"] == "critical"
    assert rows[0]["details"] == ["高风险"]
    assert rows[0]["weather_factor"] == 0.7


async def test_adaptability_save_many_empty_is_noop(session_factory):
    repo = AdaptabilityDbRepository(session_factory)
    await repo.save_many([])   # 不应抛异常


async def test_snapshot_track_roundtrip(session_factory):
    from src.domain.models import UAVHealthSnapshot
    repo = FlightLogDbRepository(session_factory)
    await repo.append_snapshot(UAVHealthSnapshot(
        uav_id="u-mon", position=Position(x=1.0, y=1.0, z=55.0),
        battery_remaining=44.0, speed=12.0, heading=180.0, timestamp=1000.0))
    await repo.append_alert("u-mon", "电量过低: 8.0Wh")

    track = await repo.get_track("u-mon")
    assert any(s.position.z == 55.0 for s in track)
    assert "电量过低: 8.0Wh" in await repo.get_alerts("u-mon")
    await repo.clear_alerts("u-mon")
    assert await repo.get_alerts("u-mon") == []
