"""任务分配测试"""

import numpy as np
import pytest

from src.domain.models import UAV, Task, Position
from src.domain.enums import TaskPriority
from src.services.task_allocation import allocate
from src.algorithms.task_allocation.differential_evolution import DiscreteDESolver


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


# ── 差分进化 (DE) ──

def _de_uav(x: float, y: float, uid: str, battery: float = 1000.0, speed: float = 10.0) -> UAV:
    return UAV(id=uid, position=Position(x=x, y=y, z=0), speed=speed, max_payload=5.0, battery=battery)


def _de_task(x: float, y: float, tid: str, time_limit: float | None = None, priority: str = "low") -> Task:
    return Task(id=tid, position=Position(x=x, y=y, z=0), payload_weight=1.0, time_limit=time_limit, priority=TaskPriority(priority))


def test_de_cost_matrix():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(30, 0, "task-0", priority="low"), _de_task(60, 0, "task-1", priority="high")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    assert solver.cost_matrix[0, 2] == pytest.approx(30.0)    # uav0→task0: 30 × 1.0
    assert solver.cost_matrix[0, 3] == pytest.approx(120.0)   # uav0→task1: 60 × 2.0
    assert solver.cost_matrix[1, 2] == pytest.approx(70.0)    # uav1→task0: 70 × 1.0


def test_de_decode_nearest_neighbor():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(50, 0, "task-0"), _de_task(90, 0, "task-1")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    decoded = solver.decode([1, 1])  # 两个任务都给 uav1
    assert decoded[0] == []
    assert decoded[1] == [1, 0]  # 从 (100,0) 出发先到 90 再到 50


def test_de_compute_path_costs():
    uavs = [_de_uav(0, 0, "uav-0")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(30, 0, "task-1")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    costs = solver.compute_path_costs({0: [0, 1]})
    assert costs[0] == pytest.approx([10.0, 20.0])
