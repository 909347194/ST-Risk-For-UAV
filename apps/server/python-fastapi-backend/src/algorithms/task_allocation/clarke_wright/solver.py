"""Clarke-Wright 节约算法求解器 — 组装 encoding / capacity 并驱动主循环"""

import numpy as np

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
    build_energy_matrix,
)
from src.algorithms.task_allocation.energy import (
    RechargePlan,
    greedy_insert_stations,
    optimal_charging_dp,
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
        stations: list | None = None,
        sigma: float | None = None,
        energy_strategy: str = "greedy",
    ):
        if energy_strategy not in ("greedy", "dp", "none"):
            raise ValueError(
                f"energy_strategy 必须为 greedy|dp|none，当前: {energy_strategy}"
            )
        if sigma is not None and sigma <= 0:
            raise ValueError(f"sigma 必须 > 0，当前: {sigma}")
        self.uavs = uavs
        self.tasks = tasks
        self.N_uav = len(uavs)
        self.N_task = len(tasks)
        self.energy_per_meter = energy_per_meter
        self.stations = stations or []
        self.sigma = sigma
        self.energy_strategy = energy_strategy
        self._energy_enabled = bool(self.stations) and energy_strategy != "none"
        if self._energy_enabled and energy_per_meter <= 0:
            raise ValueError(f"energy_per_meter 必须 > 0，当前: {energy_per_meter}")
        self.uav_max_ranges = derive_uav_ranges(uavs, uav_max_ranges, energy_per_meter)
        if self._energy_enabled:
            self.e_matrix = build_energy_matrix(uavs, tasks, self.stations, energy_per_meter)
            self.station_indices = [self.N_uav + self.N_task + k for k in range(len(self.stations))]
        else:
            self.e_matrix = None
            self.station_indices = None
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
            e_matrix=self.e_matrix,
            stations=self.stations,
            station_indices=self.station_indices,
            sigma=self.sigma,
            energy_strategy=self.energy_strategy,
            energy_per_meter=self.energy_per_meter,
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

    # ———— 能量计划 ————
    def _plan_for(self, uav_idx: int, route: list[int]) -> RechargePlan | None:
        """给定路线生成补给计划;energy 关闭时不会调用"""
        seq = [uav_idx] + [self.N_uav + tid for tid in route]
        uav = self.uavs[uav_idx]
        if self.energy_strategy == "dp":
            plan = optimal_charging_dp(
                seq, self.e_matrix, self.stations, self.station_indices,
                uav.battery, self.sigma, uav.speed, self.energy_per_meter,
            )
        else:
            plan = greedy_insert_stations(
                seq, self.e_matrix, self.stations, self.station_indices,
                uav.battery, self.sigma, uav.speed, self.energy_per_meter,
            )
        if plan is not None:
            plan.uav_id = uav.id
        return plan

    def _infeasible_plan(self, uav_idx: int, route: list[int]) -> RechargePlan:
        """插站失败且无处移交:标记不可行的占位计划(飞行代价仍给出)"""
        seq = [uav_idx] + [self.N_uav + tid for tid in route]
        uav = self.uavs[uav_idx]
        arrival_times = [0.0]
        total_energy = 0.0
        t = 0.0
        for prev, nxt in zip(seq, seq[1:]):
            total_energy += float(self.e_matrix[prev, nxt])
            t += float(self.e_matrix[prev, nxt]) / self.energy_per_meter / uav.speed
            arrival_times.append(t)
        return RechargePlan(
            uav_id=uav.id, node_seq=seq, charges=[],
            total_time=t, total_energy=total_energy,
            arrival_times=arrival_times, feasible=False,
        )

    def _energy_slack(self, uav_idx: int, routes: dict[int, list[list[int]]]) -> float:
        """能量余量 (Wh) = 电池 − 该机全部路线飞行能耗(插站前的粗估)"""
        used = 0.0
        for route in routes[uav_idx]:
            seq = [uav_idx] + [self.N_uav + tid for tid in route]
            used += sum(float(self.e_matrix[p, q]) for p, q in zip(seq, seq[1:]))
        return self.uavs[uav_idx].battery - used

    def _energy_repair(self, routes: dict[int, list[list[int]]]) -> dict[int, list[RechargePlan]]:
        """构造后修复:插站失败的任务移交给能量余量最大且不超容(航程/载荷)的目标"""
        last_moved: dict[int, int] = {}
        for _ in range(self.N_task + 1):
            moved = False
            for uav_idx in range(self.N_uav):
                for route in list(routes[uav_idx]):
                    if self._plan_for(uav_idx, route) is not None:
                        continue
                    task = route[-1]
                    targets = sorted(
                        (t for t in range(self.N_uav)
                         if t != uav_idx and last_moved.get(task) != t),
                        key=lambda t: -self._energy_slack(t, routes),
                    )
                    for target in targets:
                        if self._plan_for(target, [task]) is not None and capacity.feasible(
                            self.cost_matrix, self.N_uav, self.N_task, self.uavs, self.tasks,
                            self.uav_max_ranges, target, routes[target] + [[task]],
                        ):
                            routes[uav_idx].remove(route)
                            route.pop()
                            if route:
                                routes[uav_idx].append(route)
                            routes[target].append([task])
                            last_moved[task] = uav_idx
                            moved = True
                            break
                    if moved:
                        break
                if moved:
                    break
            if not moved:
                break
        plans: dict[int, list[RechargePlan]] = {i: [] for i in range(self.N_uav)}
        for uav_idx, route_list in routes.items():
            for route in route_list:
                plan = self._plan_for(uav_idx, route)
                plans[uav_idx].append(
                    plan if plan is not None else self._infeasible_plan(uav_idx, route)
                )
        return plans

    def build_recharge_plans(self, routes: dict[int, list[list[int]]]) -> list[RechargePlan]:
        """对外:energy 关闭返回 [];否则每路线一条计划(uav 顺序、路线顺序)"""
        if not self._energy_enabled:
            return []
        plans = self._energy_repair(routes)
        return [p for uav_idx in range(self.N_uav) for p in plans[uav_idx]]

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
    stations: list | None = None,
    sigma: float | None = None,
    energy_strategy: str = "greedy",
    **kwargs,
) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]:
    """Clarke-Wright 任务分配 — 与 hungarian/auction/de 同签名

    返回 (allocations, unassigned, plans)。allocations 按 UAV 下标、路线创建
    顺序拼接输出，保留 CW 的访问顺序；CW 覆盖全部任务，
    unassigned 恒为空。plans 为每路线一条补给计划(无 stations 时为空)。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks], []

    solver = ClarkeWrightSolver(
        uavs=uavs,
        tasks=tasks,
        uav_max_ranges=uav_max_ranges,
        energy_per_meter=energy_per_meter,
        stations=stations,
        sigma=sigma,
        energy_strategy=energy_strategy,
    )
    routes = solver.solve()
    plans = solver.build_recharge_plans(routes)  # 能量修复会就地改写 routes, 先取 plans

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
    return allocations, [], plans
