"""路径规划测试"""

from src.shared.models import Position
from src.path_planning.service import plan_path


def test_astar_straight():
    start = Position(x=0, y=0)
    goal = Position(x=10, y=0)
    plan = plan_path(
        uav_id="uav-1", task_id="task-1",
        start=start, goal=goal, obstacles=[], algorithm="astar",
    )
    assert len(plan.waypoints) >= 2
    assert plan.total_distance > 0
    assert plan.estimated_time > 0


def test_rrt_basic():
    start = Position(x=0, y=0)
    goal = Position(x=10, y=0)
    plan = plan_path(
        uav_id="uav-1", task_id="task-1",
        start=start, goal=goal, obstacles=[], algorithm="rrt",
        params={"max_iterations": 1000},
    )
    assert len(plan.waypoints) >= 2


def test_unknown_algorithm():
    start = Position(x=0, y=0)
    goal = Position(x=10, y=0)
    try:
        plan_path(
            uav_id="uav-1", task_id="task-1",
            start=start, goal=goal, obstacles=[], algorithm="nonexistent",
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
