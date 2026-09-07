"""Clarke-Wright 节约算法 — 多机多任务构造启发式

参考：Clarke G, Wright J W. Scheduling of Vehicles from a Central Depot
to a Number of Delivery Points. Operations Research, 1964.
（开放路线变体：无返程段，与 DE 适应度模型一致）

角色：为 DE 提供高质量初始解（warm_start），也可独立使用。
"""

import numpy as np

from src.domain.models import UAV, Task
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
)


class ClarkeWrightSolver:
    """Clarke-Wright 节约算法求解器

    开放路线多机场景：初始每个任务一条单点路线挂到最近 UAV，
    迭代贪心选取最大正节约值的同 UAV 路线对合并，容量约束为
    航程（≤ max_range）与载荷（总载荷 ≤ max_payload）。
    单点路线不校验自身可行性（任务本身必须被分配）。
    """

    def __init__(
        self,
        uavs: list[UAV],
        tasks: list[Task],
        uav_max_ranges: list[float] | None = None,
        energy_per_meter: float = 0.1,
    ):
        self.uavs = uavs
        self.tasks = tasks
        self.N_uav = len(uavs)
        self.N_task = len(tasks)
        self.uav_max_ranges = derive_uav_ranges(uavs, uav_max_ranges, energy_per_meter)
        self._build_cost_matrix()

    # ———— 代价矩阵 ————
    def _build_cost_matrix(self) -> None:
        self.cost_matrix = build_cost_matrix(self.uavs, self.tasks)

    # ———— 路线代价 ————
    def route_segment_costs(self, uav_idx: int, route: list[int]) -> list[float]:
        """路线逐段代价，首段从该 UAV 位置出发"""
        current = uav_idx
        seg: list[float] = []
        for tid in route:
            seg.append(float(self.cost_matrix[current, self.N_uav + tid]))
            current = self.N_uav + tid
        return seg

    # ———— 容量检查 ————
    def _feasible(self, uav_idx: int, route: list[int]) -> bool:
        """合并后航程与载荷约束检查"""
        if sum(self.route_segment_costs(uav_idx, route)) > self.uav_max_ranges[uav_idx]:
            return False
        payload = sum(self.tasks[tid].payload_weight for tid in route)
        if payload > self.uavs[uav_idx].max_payload:
            return False
        return True

    # ———— 求解 ————
    def solve(self) -> dict[int, list[list[int]]]:
        """返回 {uav_idx: [路线...]}，每条路线为有序任务下标列表"""
        routes: dict[int, list[list[int]]] = {i: [] for i in range(self.N_uav)}
        if not self.uavs or not self.tasks:
            return routes

        # 初始: 每个任务一条单点路线，挂到最近 UAV
        for tid in range(self.N_task):
            best_uav = int(np.argmin(self.cost_matrix[: self.N_uav, self.N_uav + tid]))
            routes[best_uav].append([tid])

        # 迭代贪心: 每次取最大正节约值的可行合并
        while True:
            best: tuple[float, int, int, int] | None = None  # (savings, uav_idx, a, b)
            for uav_idx, route_list in routes.items():
                depot = uav_idx
                for a in range(len(route_list)):
                    for b in range(len(route_list)):
                        if a == b:
                            continue
                        i = route_list[a][-1]  # 路线 a 的尾
                        j = route_list[b][0]   # 路线 b 的头
                        s = (
                            self.cost_matrix[depot, self.N_uav + i]
                            + self.cost_matrix[depot, self.N_uav + j]
                            - self.cost_matrix[self.N_uav + i, self.N_uav + j]
                        )
                        if s <= 0:
                            continue
                        merged = route_list[a] + route_list[b]
                        if not self._feasible(uav_idx, merged):
                            continue
                        if best is None or float(s) > best[0]:
                            best = (float(s), uav_idx, a, b)
            if best is None:
                break
            _, uav_idx, a, b = best
            route_list = routes[uav_idx]
            merged = route_list[a] + route_list[b]
            routes[uav_idx] = [r for idx, r in enumerate(route_list) if idx not in (a, b)]
            routes[uav_idx].append(merged)
        return routes

    # ———— 转为 DE 个体编码 ————
    def to_individual(self) -> list[int]:
        """路线 → DE 整数编码: gene[tid] = 该任务所属 UAV 下标"""
        routes = self.solve()
        individual = [0] * self.N_task
        for uav_idx, route_list in routes.items():
            for route in route_list:
                for tid in route:
                    individual[tid] = uav_idx
        return individual
