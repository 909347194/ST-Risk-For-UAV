"""任务分配算法"""

from src.algorithms.registry import register, AlgorithmCategory
from src.algorithms.task_allocation.hungarian import hungarian_allocate
from src.algorithms.task_allocation.auction import auction_allocate
from src.algorithms.task_allocation.differential_evolution import de_allocate
from src.algorithms.task_allocation.clarke_wright import clarke_wright_allocate


def _register() -> None:
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "hungarian",
        hungarian_allocate,
        {
            "name": "hungarian",
            "description": "匈牙利算法 — 最优一对一匹配，适合任务数≈无人机数的场景",
            "params_schema": None,
        },
    )
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "auction",
        auction_allocate,
        {
            "name": "auction",
            "description": "拍卖算法 — 分布式竞价，适合大规模动态场景",
            "params_schema": {
                "max_iterations": {"type": "integer", "default": 100, "description": "最大迭代轮数"},
            },
        },
    )
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "de",
        de_allocate,
        {
            "name": "de",
            "description": "离散差分进化 — 多机多任务分配，约束感知适应度，自适应 F/CR",
            "params_schema": {
                "pop_size": {"type": "integer", "default": 50, "description": "种群规模"},
                "generations": {"type": "integer", "default": 100, "description": "进化代数"},
                "F_init": {"type": "number", "default": 0.9, "description": "差分权重初值"},
                "CR_init": {"type": "number", "default": 0.5, "description": "交叉率初值"},
                "elite_guide_prob": {"type": "number", "default": 0.3, "description": "精英引导变异概率"},
                "heuristic_ratio": {"type": "number", "default": 0.2, "description": "启发式初始化占比"},
                "uav_max_ranges": {"type": "array", "default": None, "description": "每机最大航程 (m)，缺省按电池推算"},
                "energy_per_meter": {"type": "number", "default": 0.1, "description": "能耗率 (Wh/m)"},
                "seed": {"type": "integer", "default": None, "description": "随机种子"},
            },
        },
    )
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "cw",
        clarke_wright_allocate,
        {
            "name": "cw",
            "description": "Clarke-Wright 节约算法 — 构造启发式，多机多任务初始解 / DE 热启动",
            "params_schema": {
                "uav_max_ranges": {"type": "array", "default": None, "description": "每机最大航程 (m)，缺省按电池推算"},
                "energy_per_meter": {"type": "number", "default": 0.1, "description": "能耗率 (Wh/m)"},
            },
        },
    )
