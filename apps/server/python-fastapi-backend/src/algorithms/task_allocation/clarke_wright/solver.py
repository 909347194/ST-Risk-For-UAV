"""Clarke-Wright 节约算法求解器 — 组装 encoding / capacity 并驱动主循环"""

import numpy as np

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
)

from . import capacity, encoding


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
        return encoding.route_segment_costs(
            self.cost_matrix, self.N_uav, self.N_task, uav_idx, route
        )

    # ———— 容量检查 ————
    def _feasible(self, uav_idx: int, route_list: list[list[int]]) -> bool:
        """每机总量容量检查：全部路线总航程 ≤ max_range 且总载荷 ≤ max_payload"""
        return capacity.feasible(
            self.cost_matrix,
            self.N_uav,
            self.N_task,
            self.uavs,
            self.tasks,
            self.uav_max_ranges,
            uav_idx,
            route_list,
        )

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
                        other_routes = [
                            route_list[idx]
                            for idx in range(len(route_list))
                            if idx not in (a, b)
                        ]
                        if not self._feasible(uav_idx, other_routes + [merged]):
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

        self._rebalance(routes)
        return routes

    # ———— 容量修复 ————
    def _rebalance(self, routes: dict[int, list[list[int]]]) -> None:
        """构造后修复：超容 UAV 路线末尾任务移交给最小代价增量且不超容的目标"""
        capacity.rebalance(
            self.cost_matrix,
            self.N_uav,
            self.N_task,
            self.uavs,
            self.tasks,
            self.uav_max_ranges,
            routes,
        )

    # ———— 转为 DE 个体编码 ————
    def to_individual(self) -> list[int]:
        """路线 → DE 整数编码: gene[tid] = 该任务所属 UAV 下标"""
        routes = self.solve()
        return encoding.to_individual(self.cost_matrix, self.N_uav, self.N_task, routes)


def clarke_wright_allocate(
    uavs: list[UAV],
    tasks: list[Task],
    uav_max_ranges: list[float] | None = None,
    energy_per_meter: float = 0.1,
    **kwargs,
) -> tuple[list[TaskAllocation], list[str]]:
    """Clarke-Wright 任务分配 — 与 hungarian/auction/de 同签名

    返回 (allocations, unassigned)。allocations 按 UAV 下标、路线创建
    顺序拼接输出，保留 CW 的访问顺序；CW 覆盖全部任务，
    unassigned 恒为空。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks]

    solver = ClarkeWrightSolver(
        uavs=uavs,
        tasks=tasks,
        uav_max_ranges=uav_max_ranges,
        energy_per_meter=energy_per_meter,
    )
    routes = solver.solve()

    allocations: list[TaskAllocation] = []
    for uav_idx in range(len(uavs)):
        uav = uavs[uav_idx]
        for route in routes[uav_idx]:
            seg_costs = solver.route_segment_costs(uav_idx, route)
            for k, tid in enumerate(route):
                allocations.append(
                    TaskAllocation(
                        uav_id=uav.id,
                        task_id=tasks[tid].id,
                        estimated_cost=seg_costs[k],
                    )
                )
    return allocations, []
