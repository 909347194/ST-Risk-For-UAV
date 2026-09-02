"""新增业务模块测试"""

from src.models.models import UAV, Task, Position, Obstacle
from src.models.enums import UAVStatus, RiskLevel
from src.services.uav_resource import register_uav, get_uav, list_uavs, update_uav_status
from src.services.task_adaptability import evaluate, evaluate_all
from src.services.risk_assessment import assess
from src.services.flight_monitoring import record_snapshot, get_track
from src.models.models import UAVHealthSnapshot


def _make_uav(uid: str = "uav-1") -> UAV:
    return UAV(id=uid, position=Position(x=0, y=0), speed=10.0, max_payload=5.0, battery=100.0)


def _make_task(tid: str = "task-1") -> Task:
    return Task(id=tid, position=Position(x=50, y=50), payload_weight=1.0)


# ── ① 资源管理 ──

def test_register_and_get():
    uav = _make_uav()
    register_uav(uav)
    result = get_uav("uav-1")
    assert result.id == "uav-1"


def test_list_by_status():
    register_uav(_make_uav("a"))
    register_uav(_make_uav("b"))
    update_uav_status("b", UAVStatus.IN_FLIGHT)
    idle = list_uavs(UAVStatus.IDLE)
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

def test_snapshot_record():
    snap = UAVHealthSnapshot(
        uav_id="uav-1", position=Position(x=10, y=20, z=50),
        battery_remaining=80.0, speed=5.0, heading=90.0, timestamp=1.0,
    )
    result = record_snapshot(snap)
    assert result.uav_id == "uav-1"

    track = get_track("uav-1")
    assert len(track) >= 1
