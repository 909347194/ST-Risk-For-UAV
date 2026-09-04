"""任务分配测试"""

import numpy as np
import pytest

from src.domain.models import UAV, Task, Position
from src.domain.enums import TaskPriority
from src.services.task_allocation import allocate
from src.algorithms.task_allocation.differential_evolution import DiscreteDESolver, de_allocate


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


def test_de_init_population():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = DiscreteDESolver(uavs, tasks, pop_size=20, seed=0)
    pop = solver._init_population()
    assert pop.shape == (20, 3)
    assert ((pop >= 0) & (pop < 2)).all()


def test_de_adaptive_params():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0")]
    solver = DiscreteDESolver(uavs, tasks, generations=10, seed=0)
    F0, CR0 = solver._adaptive_params(0)
    assert F0 == pytest.approx(0.9)
    assert CR0 == pytest.approx(0.5)
    F9, CR9 = solver._adaptive_params(9)
    assert F9 == pytest.approx(0.36)
    assert CR9 == pytest.approx(0.9)


def test_de_repair():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    ind = np.array([-0.4, 0.4, 1.6, 2.9])
    assert solver._repair(ind).tolist() == [0, 0, 1, 1]


def test_de_crossover_copies_at_least_one_gene():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    target = solver._init_population()[0]
    mutant = target.astype(float) + 100.0  # 任何被复制的位都必然不同于 target
    trial = solver._crossover(target, mutant, 0)
    assert not np.array_equal(trial, target)


def test_de_crossover_preserves_fractional_genes():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    target = np.array([0, 0, 0])
    mutant = target.astype(float) + 0.6  # |mutant−target| < 1：旧实现会截断退化为 target
    trial = solver._crossover(target, mutant, 0)
    assert trial.dtype == float
    assert not np.array_equal(trial, target)  # j_rand 保证在连续空间成立


def test_de_evaluate_constrained_no_violation():
    uav = _de_uav(0, 0, "uav-0", battery=1000.0, speed=10.0)  # 默认航程 = 1000/0.1 = 10000
    task = _de_task(10, 0, "task-0")  # 无 time_limit
    solver = DiscreteDESolver([uav], [task], seed=0)
    fitness = solver.evaluate_constrained([0])
    # path_cost=10, flight_time=1.0, 违反量=0（单机 var=0）
    assert fitness == pytest.approx(10.0 + 0.5 * 1.0)  # 10.5


def test_de_evaluate_range_violation():
    uav = _de_uav(0, 0, "uav-0", battery=1000.0, speed=10.0)
    task = _de_task(10, 0, "task-0")
    solver = DiscreteDESolver([uav], [task], uav_max_ranges=[5.0], seed=0)
    fitness = solver.evaluate_constrained([0])
    # 违反量 = (10-5)/5 = 1.0
    assert fitness == pytest.approx(10.0 + 0.5 + 500.0 * 1.0)  # 510.5


def test_de_evaluate_deadline_violation():
    uav = _de_uav(0, 0, "uav-0", battery=1000.0, speed=10.0)
    task = _de_task(10, 0, "task-0", time_limit=0.5)
    solver = DiscreteDESolver([uav], [task], seed=0)
    fitness = solver.evaluate_constrained([0])
    # flight_time=1.0 > 0.5 → 违反量 0.5
    assert fitness == pytest.approx(10.0 + 0.5 + 500.0 * 0.5)  # 260.5


def test_de_evaluate_basic_prefers_shorter_path():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(5, 0, "task-0"), _de_task(105, 0, "task-1")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    optimal = solver.evaluate([0, 1])   # 各自就近
    crossed = solver.evaluate([1, 0])   # 交叉远飞
    assert optimal < crossed


def test_de_find_convergence():
    assert DiscreteDESolver._find_convergence([1.0, 1.0, 1.0, 1.0, 1.0, 1.0]) == 0
    assert DiscreteDESolver._find_convergence([0.0, 0.1, 0.2, 0.3, 0.4, 0.5]) == 5


def test_de_solve_covers_tasks_and_stats():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = DiscreteDESolver(uavs, tasks, pop_size=20, generations=30, seed=0)
    allocation, stats = solver.solve()
    assigned = sorted(t for seq in allocation.values() for t in seq)
    assert assigned == [0, 1, 2]
    assert set(allocation.keys()) == {0, 1}
    assert stats["algorithm"] == "de"
    assert stats["convergence_gen"] <= stats["total_generations"]
    assert len(stats["history_min"]) == stats["total_generations"] + 1
    assert stats["time_seconds"] >= 0
    assert stats["best_cost"] > 0


def test_de_solve_seed_reproducible():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    s1 = DiscreteDESolver(uavs, tasks, seed=42)
    s2 = DiscreteDESolver(uavs, tasks, seed=42)
    a1, _ = s1.solve()
    a2, _ = s2.solve()
    assert a1 == a2


def test_de_basic():
    uavs = _make_uavs(2)
    tasks = _make_tasks(3)
    allocations, unassigned = de_allocate(uavs, tasks, seed=42, pop_size=20, generations=30)
    assert unassigned == []
    pairs = {(a.uav_id, a.task_id) for a in allocations}
    assert len(pairs) == 3  # 全分配、无重复对
    assert all(a.estimated_cost >= 0 for a in allocations)


def test_de_empty_inputs():
    uavs = [_de_uav(0, 0, "uav-0")]
    task = _de_task(10, 0, "task-0")
    allocations, unassigned = de_allocate([], [task])
    assert allocations == [] and unassigned == ["task-0"]
    allocations, unassigned = de_allocate(uavs, [])
    assert allocations == [] and unassigned == []


def test_de_ignores_unknown_kwargs():
    uavs = _make_uavs(2)
    tasks = _make_tasks(2)
    allocations, _ = de_allocate(uavs, tasks, seed=0, unknown_thing=123)
    assert len(allocations) == 2


def test_de_cluster_reasonable():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [
        _de_task(5, 5, "task-0"),
        _de_task(-5, 5, "task-1"),
        _de_task(105, 5, "task-2"),
        _de_task(95, 5, "task-3"),
    ]
    allocations, unassigned = de_allocate(uavs, tasks, pop_size=40, generations=100, seed=0)
    assert unassigned == []
    by_task = {a.task_id: a.uav_id for a in allocations}
    assert by_task["task-0"] == "uav-0"
    assert by_task["task-1"] == "uav-0"
    assert by_task["task-2"] == "uav-1"
    assert by_task["task-3"] == "uav-1"


def test_de_seed_reproducible():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    a1, _ = de_allocate(uavs, tasks, seed=42)
    a2, _ = de_allocate(uavs, tasks, seed=42)
    key = lambda a: sorted((x.uav_id, x.task_id, x.estimated_cost) for x in a)
    assert key(a1) == key(a2)


def test_de_via_service():
    uavs = _make_uavs(2)
    tasks = _make_tasks(3)
    allocations, unassigned = allocate(uavs, tasks, algorithm="de", params={"seed": 0, "pop_size": 10, "generations": 10})
    assert len(allocations) == 3
    assert unassigned == []


def test_de_listed_in_algorithms():
    from src.services import task_allocation as service
    names = [a["name"] for a in service.list_available_algorithms()]
    assert "de" in names


def test_de_invalid_params_raise():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0")]
    with pytest.raises(ValueError):
        DiscreteDESolver(uavs, tasks, pop_size=3)
    with pytest.raises(ValueError):
        DiscreteDESolver(uavs, tasks, uav_max_ranges=[100.0])  # 长度 1 ≠ N_uav 2
    with pytest.raises(ValueError):
        DiscreteDESolver(uavs, tasks, uav_max_ranges=[0.0, 100.0])
    with pytest.raises(ValueError):
        DiscreteDESolver(uavs, tasks, heuristic_ratio=1.5)
