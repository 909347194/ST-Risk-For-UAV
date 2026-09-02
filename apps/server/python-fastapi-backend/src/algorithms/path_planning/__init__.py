"""路径规划算法"""

from src.algorithms.registry import register, AlgorithmCategory
from src.algorithms.path_planning.astar import astar_plan
from src.algorithms.path_planning.rrt import rrt_plan


def _register() -> None:
    register(
        AlgorithmCategory.PATH_PLANNING,
        "astar",
        astar_plan,
        {
            "name": "astar",
            "description": "A* 栅格搜索 — 最优路径，适合静态已知环境",
            "params_schema": {
                "grid_resolution": {"type": "number", "default": 1.0, "description": "栅格分辨率 (m)"},
            },
        },
    )
    register(
        AlgorithmCategory.PATH_PLANNING,
        "rrt",
        rrt_plan,
        {
            "name": "rrt",
            "description": "快速随机树 — 适合高维空间和复杂障碍物环境",
            "params_schema": {
                "step_size": {"type": "number", "default": 2.0, "description": "步长 (m)"},
                "max_iterations": {"type": "integer", "default": 5000, "description": "最大迭代次数"},
                "goal_threshold": {"type": "number", "default": 2.0, "description": "到达目标的判定距离 (m)"},
            },
        },
    )
