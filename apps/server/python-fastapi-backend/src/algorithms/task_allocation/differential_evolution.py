"""离散差分进化 (DE) 任务分配算法

参考：
  樊国政等《基于改进差分进化算法的同构无人机任务分配》
  Zhao et al., Acta Automatica Sinica, 2012, 38(12): 2038-2048.

核心思想：整数编码 + 连续空间差分变异 + 取整钳位修复
"""
import time

import numpy as np

from src.domain.models import UAV, Task, TaskAllocation
from src.utils.utils import distance

PRIORITY_WEIGHT = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}


class DiscreteDESolver:
    """离散差分进化求解器 — 多机多任务分配

    改进点（同参考实现）:
    1. 自适应 F/CR: F↓ (探索→开发), CR↑
    2. 约束感知适应度: 航程 / 任务 deadline / 负载均衡
    3. 精英引导变异: DE/current-to-best/1
    4. 启发式初始化: 贪心最近邻构造部分初始解
    5. seed 可复现（np.random.default_rng）
    """

    def __init__(
        self,
        uavs: list[UAV],
        tasks: list[Task],
        pop_size: int = 50,
        generations: int = 100,
        F_init: float = 0.9,
        CR_init: float = 0.5,
        elite_guide_prob: float = 0.3,
        heuristic_ratio: float = 0.2,
        uav_max_ranges: list[float] | None = None,
        energy_per_meter: float = 0.1,
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 1.0,
        penalty_weight: float = 500.0,
        seed: int | None = None,
    ):
        self.uavs = uavs
        self.tasks = tasks
        self.N_uav = len(uavs)
        self.N_task = len(tasks)
        self.pop_size = pop_size
        self.gens = generations
        self.F_init = F_init
        self.CR_init = CR_init
        self.elite_guide_prob = elite_guide_prob
        self.heuristic_ratio = heuristic_ratio
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.penalty_weight = penalty_weight
        self.rng = np.random.default_rng(seed)

        # 最大航程: 显式参数优先, 否则按电池/能耗率推算
        if uav_max_ranges is not None:
            self.uav_max_ranges = list(uav_max_ranges)
        else:
            self.uav_max_ranges = [
                u.battery / energy_per_meter if energy_per_meter > 0 else float("inf")
                for u in uavs
            ]

        self._build_cost_matrix()

    # ———— 代价矩阵 ————
    def _build_cost_matrix(self) -> None:
        points = [u.position for u in self.uavs] + [t.position for t in self.tasks]
        n = len(points)
        self.cost_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                d = distance(points[i], points[j])
                if j >= self.N_uav:
                    task = self.tasks[j - self.N_uav]
                    d *= PRIORITY_WEIGHT.get(task.priority.value, 1.0)
                self.cost_matrix[i, j] = d

    # ———— 解码 ————
    def decode(self, individual: list[int] | np.ndarray) -> dict[int, list[int]]:
        """整数编码 → {uav_id: [task_id, ...]} (最近邻排序)

        个体: [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]
        """
        uav_tasks: dict[int, list[int]] = {i: [] for i in range(self.N_uav)}
        for task_id, uav_id in enumerate(individual):
            uav_tasks[int(uav_id)].append(task_id)

        sorted_tasks: dict[int, list[int]] = {}
        for uav_id, task_list in uav_tasks.items():
            if not task_list:
                sorted_tasks[uav_id] = []
                continue
            current_idx = uav_id  # 从 UAV 位置出发
            seq: list[int] = []
            remaining = task_list.copy()
            while remaining:
                nearest = min(
                    remaining,
                    key=lambda tid: self.cost_matrix[current_idx, self.N_uav + tid],
                )
                seq.append(nearest)
                remaining.remove(nearest)
                current_idx = self.N_uav + nearest
            sorted_tasks[uav_id] = seq
        return sorted_tasks

    # ———— 路径代价 ————
    def compute_path_costs(
        self, uav_task_dict: dict[int, list[int]]
    ) -> dict[int, list[float]]:
        """计算每架 UAV 任务序列的逐段代价"""
        costs: dict[int, list[float]] = {}
        for uav_id, seq in uav_task_dict.items():
            if not seq:
                costs[uav_id] = []
                continue
            current_idx = uav_id
            seg: list[float] = []
            for tid in seq:
                seg.append(float(self.cost_matrix[current_idx, self.N_uav + tid]))
                current_idx = self.N_uav + tid
            costs[uav_id] = seg
        return costs
