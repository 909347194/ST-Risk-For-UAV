"""新增业务模块测试"""

from src.domain.enums import RiskLevel, UAVStatus
from src.domain.models import UAV, Obstacle, Position, Task, UAVHealthSnapshot
from src.services.flight_monitoring import get_track, record_snapshot
from src.services.risk_assessment import assess
from src.services.task_adaptability import evaluate
from src.services.uav_resource import (
    get_uav,
    list_uavs,
    register_uav,
    update_uav_status,
)


def _make_uav(uid: str = "uav-1") -> UAV:
    return UAV(id=uid, position=Position(x=0, y=0), speed=10.0, max_payload=5.0, battery=100.0)


def _make_task(tid: str = "task-1") -> Task:
    return Task(id=tid, position=Position(x=50, y=50), payload_weight=1.0)


# ── ① 资源管理 ──

async def test_register_and_get():
    uav = _make_uav()
    await register_uav(uav)
    result = await get_uav("uav-1")
    assert result.id == "uav-1"


async def test_list_by_status():
    await register_uav(_make_uav("a"))
    await register_uav(_make_uav("b"))
    await update_uav_status("b", UAVStatus.IN_FLIGHT)
    idle = await list_uavs(UAVStatus.IDLE)
    assert all(u.status == UAVStatus.IDLE for u in idle)


# ── ② 适配评估 ──

def test_evaluate_capable():
    uav = _make_uav()
    task = _make_task()
    result = evaluate(uav, task)
    assert result.capable is True
    assert result.payload_ok is True


def test_evaluate_payload_fail():
    uav = UAV(id="weak", position=Position(x=0, y=0), speed=10.0, max_payload=0.1, battery=100.0)
    task = Task(id="heavy", position=Position(x=5, y=5), payload_weight=10.0)
    result = evaluate(uav, task)
    assert result.payload_ok is False
    assert result.capable is False


# ── ③ 风险评估 ──

def test_risk_no_obstacles():
    uav = _make_uav()
    task = _make_task()
    result = assess(uav, task)
    assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)


def test_risk_with_obstacle():
    uav = _make_uav()
    task = _make_task()
    obs = Obstacle(center=Position(x=1, y=1), radius=5.0)
    result = assess(uav, task, obstacles=[obs])
    assert result.collision_risk > 0


# ── ⑥ 飞行监控 ──

async def test_snapshot_record():
    snap = UAVHealthSnapshot(
        uav_id="uav-1", position=Position(x=10, y=20, z=50),
        battery_remaining=80.0, speed=5.0, heading=90.0, timestamp=1.0,
    )
    result = await record_snapshot(snap)
    assert result.uav_id == "uav-1"

    track = await get_track("uav-1")
    assert len(track) >= 1


async def test_record_snapshot_persists_anomaly_fields(monkeypatch):
    """回归：异常判定必须发生在 append_snapshot 之前。

    db 仓储的映射器在插入时复制对象字段，若先落库再判定，
    落库行将永远是 is_anomaly=False / 空 reasons（memory 仓储存引用，
    恰好掩盖此 bug——测试用深拷贝的记录仓储暴露它）。
    """
    saved: list[UAVHealthSnapshot] = []

    class RecordingRepo:
        def __init__(self) -> None:
            self.alerts: list[tuple[str, str]] = []

        async def append_snapshot(self, snap: UAVHealthSnapshot) -> None:
            saved.append(snap.model_copy(deep=True))

        async def append_alert(self, uav_id: str, alert: str) -> None:
            self.alerts.append((uav_id, alert))

    repo = RecordingRepo()
    monkeypatch.setattr(
        "src.repositories.factory.get_flight_log_repository", lambda: repo
    )

    snap = UAVHealthSnapshot(
        uav_id="uav-1", position=Position(x=10, y=20, z=50),
        battery_remaining=8.0, speed=5.0, heading=90.0, timestamp=1.0,
    )
    await record_snapshot(snap)

    assert saved[0].is_anomaly is True
    assert saved[0].anomaly_reasons == ["电量过低: 8.0Wh"]
    assert repo.alerts == [("uav-1", "电量过低: 8.0Wh")]
