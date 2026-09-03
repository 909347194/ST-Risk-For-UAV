"""任务分配测试"""

from src.domain.models import UAV, Task, Position
from src.services.task_allocation import allocate


def _make_uavs(n: int) -> list[UAV]:
    return [
        UAV(id=f"uav-{i}", position=Position(x=i * 10, y=0, z=0), speed=10.0, max_payload=5.0, battery=100.0)
        for i in range(n)
    ]


def _make_tasks(n: int) -> list[Task]:
    return [
        Task(id=f"task-{i}", position=Position(x=i * 10 + 5, y=20, z=0), payload_weight=1.0)
        for i in range(n)
    ]


def test_hungarian_basic():
    uavs = _make_uavs(3)
    tasks = _make_tasks(3)
    allocations, unassigned = allocate(uavs, tasks, algorithm="hungarian")
    assert len(allocations) == 3
    assert len(unassigned) == 0


def test_auction_basic():
    uavs = _make_uavs(3)
    tasks = _make_tasks(2)
    allocations, unassigned = allocate(uavs, tasks, algorithm="auction")
    assert len(allocations) == 2


def test_more_tasks_than_uavs():
    uavs = _make_uavs(2)
    tasks = _make_tasks(5)
    allocations, unassigned = allocate(uavs, tasks, algorithm="hungarian")
    assert len(allocations) == 2
    assert len(unassigned) == 3


def test_unknown_algorithm():
    from src.domain.exceptions import AlgorithmNotFoundError

    uavs = _make_uavs(1)
    tasks = _make_tasks(1)
    try:
        allocate(uavs, tasks, algorithm="nonexistent")
        assert False, "Should have raised AlgorithmNotFoundError"
    except AlgorithmNotFoundError:
        pass
