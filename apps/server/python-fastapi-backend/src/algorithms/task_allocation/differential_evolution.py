"""离散差分进化 (DE) 任务分配算法

参考：
  樊国政等《基于改进差分进化算法的同构无人机任务分配》
  Zhao et al., Acta Automatica Sinica, 2012, 38(12): 2038-2048.

核心思想：整数编码 + 连续空间差分变异 + 取整钳位修复
"""
import time

import numpy as np

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
)


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
        warm_start: list[int] | None = None,
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

        # 参数校验 — 无效值提前以清晰错误拒绝，而非在进化中途崩溃
        if self.pop_size < 4:
            raise ValueError(f"pop_size 必须 >= 4（变异需 3 个互异候选个体），当前: {self.pop_size}")
        if not 0.0 < self.heuristic_ratio <= 1.0:
            raise ValueError(f"heuristic_ratio 必须在 (0, 1] 区间，当前: {self.heuristic_ratio}")

        # warm_start 校验: 长度与值域
        if warm_start is not None:
            if len(warm_start) != self.N_task:
                raise ValueError(
                    f"warm_start 长度必须等于任务数 ({self.N_task})，当前: {len(warm_start)}"
                )
            if any(not 0 <= g < self.N_uav for g in warm_start):
                raise ValueError(f"warm_start 基因值必须在 [0, {self.N_uav}) 区间")
        self.warm_start = warm_start

        # 最大航程: 显式参数优先, 否则按电池/能耗率推算（校验在公共函数内）
        self.uav_max_ranges = derive_uav_ranges(uavs, uav_max_ranges, energy_per_meter)

        self._build_cost_matrix()

    # ———— 代价矩阵 ————
    def _build_cost_matrix(self) -> None:
        self.cost_matrix = build_cost_matrix(self.uavs, self.tasks)

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

    # ———— 自适应参数 ————
    def _adaptive_params(self, gen: int) -> tuple[float, float]:
        progress = gen / max(self.gens - 1, 1)
        F = self.F_init * (1.0 - 0.6 * progress)   # 0.9 → 0.36
        CR = self.CR_init + 0.4 * progress          # 0.5 → 0.9
        return F, CR

    # ———— 启发式初始化 ————
    def _init_population(self) -> np.ndarray:
        if self.warm_start is not None:
            return self._init_population_with_warm_start()

        n_heuristic = max(1, int(self.pop_size * self.heuristic_ratio))
        n_random = self.pop_size - n_heuristic
        pop: list[np.ndarray] = []

        # 贪心构造 + 扰动
        for _ in range(n_heuristic):
            ind = np.zeros(self.N_task, dtype=int)
            for tid in range(self.N_task):
                best_uav = int(np.argmin(self.cost_matrix[: self.N_uav, self.N_uav + tid]))
                ind[tid] = best_uav
            # 10% 随机翻转
            flip_mask = self.rng.random(self.N_task) < 0.1
            ind[flip_mask] = self.rng.integers(0, self.N_uav, size=int(flip_mask.sum()))
            pop.append(ind)

        # 随机个体
        for _ in range(n_random):
            pop.append(self.rng.integers(0, self.N_uav, size=self.N_task))

        return np.array(pop)

    # ———— 热启动初始化 ————
    def _init_population_with_warm_start(self) -> np.ndarray:
        """种群[0] = warm_start；其余 heuristic_ratio 比例为扰动个体，剩余随机"""
        pop: list[np.ndarray] = [np.array(self.warm_start, dtype=int)]
        n_perturbed = max(0, int((self.pop_size - 1) * self.heuristic_ratio))
        n_random = self.pop_size - 1 - n_perturbed
        base = np.array(self.warm_start, dtype=int)
        for _ in range(n_perturbed):
            ind = base.copy()
            flip_mask = self.rng.random(self.N_task) < 0.1
            ind[flip_mask] = self.rng.integers(0, self.N_uav, size=int(flip_mask.sum()))
            pop.append(ind)
        for _ in range(n_random):
            pop.append(self.rng.integers(0, self.N_uav, size=self.N_task))
        return np.array(pop)

    # ———— 精英引导变异 ————
    def _mutate(
        self,
        population: np.ndarray,
        idx: int,
        best_idx: int,
        gen: int,
    ) -> np.ndarray:
        F, _ = self._adaptive_params(gen)
        candidates = [i for i in range(self.pop_size) if i != idx]

        if self.rng.random() < self.elite_guide_prob and best_idx != idx:
            # DE/current-to-best/1
            r1, r2 = population[
                self.rng.choice(candidates, 2, replace=False)
            ]
            mutant = (
                population[idx].astype(float)
                + F * (population[best_idx].astype(float) - population[idx].astype(float))
                + F * (r1.astype(float) - r2.astype(float))
            )
        else:
            # DE/rand/1
            r1, r2, r3 = population[
                self.rng.choice(candidates, 3, replace=False)
            ]
            mutant = r1.astype(float) + F * (r2.astype(float) - r3.astype(float))

        return mutant

    # ———— 二项式交叉 ————
    def _crossover(
        self,
        target: np.ndarray,
        mutant: np.ndarray,
        gen: int,
    ) -> np.ndarray:
        _, CR = self._adaptive_params(gen)
        trial = target.astype(float)
        j_rand = int(self.rng.integers(self.N_task))
        rand = self.rng.random(self.N_task)
        for j in range(self.N_task):
            if rand[j] < CR or j == j_rand:
                trial[j] = mutant[j]
        return trial

    # ———— 修复 ————
    def _repair(self, individual: np.ndarray) -> np.ndarray:
        """取整 → 钳位"""
        return np.clip(np.round(individual).astype(int), 0, self.N_uav - 1)

    # ———— 基础适应度 ————
    def evaluate(self, individual: list[int]) -> float:
        """基础适应度 = 总路径代价 + 超航程惩罚"""
        uav_task_dict = self.decode(individual)
        costs_dict = self.compute_path_costs(uav_task_dict)
        total_cost = 0.0
        for uav_id, seq in uav_task_dict.items():
            if not seq:
                continue
            seg_cost = sum(costs_dict[uav_id])
            if seg_cost > self.uav_max_ranges[uav_id]:
                total_cost += seg_cost + 10000.0  # 超航程惩罚
            else:
                total_cost += seg_cost
        return total_cost

    # ———— 约束感知适应度 (Zhao et al. 2012, Eq. 23) ————
    def evaluate_constrained(
        self,
        individual: list[int],
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 1.0,
        penalty_weight: float = 500.0,
    ) -> float:
        """增强适应度 — 多约束惩罚

        fitness = alpha·Σ(path_cost) + beta·max_flight_time
                  + gamma·penalty_weight·Σ(constraint_violations)

        约束:
          1. 最大航程约束
          2. 任务 deadline 约束 (Task.time_limit)
          3. 负载均衡约束
        """
        uav_task_dict = self.decode(individual)
        costs_dict = self.compute_path_costs(uav_task_dict)
        total_path_cost = 0.0
        max_flight_time = 0.0
        violations = 0.0

        for uav_id, seq in uav_task_dict.items():
            if not seq:
                continue
            path_cost = sum(costs_dict[uav_id])
            total_path_cost += path_cost

            speed = self.uavs[uav_id].speed
            flight_time = path_cost / speed if speed > 0 else 0.0
            max_flight_time = max(max_flight_time, flight_time)

            # 约束 1: 最大航程
            max_range = self.uav_max_ranges[uav_id]
            if path_cost > max_range:
                violations += (path_cost - max_range) / max_range

        # 约束 2: 任务 deadline（累计到达时刻）
        for uav_id, seq in uav_task_dict.items():
            speed = self.uavs[uav_id].speed
            cumulative = 0.0
            for k, tid in enumerate(seq):
                if speed > 0:
                    cumulative += costs_dict[uav_id][k] / speed
                task = self.tasks[tid]
                if task.time_limit is not None and cumulative > task.time_limit:
                    violations += 0.5

        # 约束 3: 负载均衡
        task_counts = [len(seq) for seq in uav_task_dict.values()]
        if task_counts:
            violations += float(np.var(task_counts)) * 0.01

        fitness = (
            alpha * total_path_cost
            + beta * max_flight_time
            + gamma * penalty_weight * violations
        )
        return fitness

    # ———— 适应度 ————
    def _fitness(self, individual: np.ndarray) -> float:
        return self.evaluate_constrained(
            list(individual),
            alpha=self.alpha,
            beta=self.beta,
            gamma=self.gamma,
            penalty_weight=self.penalty_weight,
        )

    # ———— 收敛检测 ————
    @staticmethod
    def _find_convergence(history_min: list[float], tol: float = 0.01) -> int:
        for i in range(len(history_min) - 5):
            if abs(history_min[i] - history_min[i + 5]) < tol:
                return i
        return len(history_min) - 1

    # ———— 主循环 ————
    def solve(self) -> tuple[dict[int, list[int]], dict]:
        t0 = time.perf_counter()

        population = self._init_population()
        fitness = np.array([self._fitness(ind) for ind in population])

        best_idx = int(np.argmin(fitness))
        best_ind = population[best_idx].copy()
        best_cost = float(fitness[best_idx])

        history_min = [best_cost]
        history_avg = [float(np.mean(fitness))]

        for gen in range(self.gens):
            for i in range(self.pop_size):
                mutant = self._mutate(population, i, best_idx, gen)
                trial_cont = self._crossover(population[i], mutant, gen)
                trial_int = self._repair(trial_cont)
                trial_fit = self._fitness(trial_int)

                if trial_fit <= fitness[i]:
                    population[i] = trial_int
                    fitness[i] = trial_fit
                    if trial_fit < best_cost:
                        best_ind = trial_int.copy()
                        best_cost = trial_fit

            history_min.append(best_cost)
            history_avg.append(float(np.mean(fitness)))

        elapsed = time.perf_counter() - t0
        best_allocation = self.decode(list(best_ind))
        convergence_gen = self._find_convergence(history_min)

        return best_allocation, {
            "algorithm": "de",
            "best_cost": best_cost,
            "convergence_gen": convergence_gen,
            "total_generations": self.gens,
            "time_seconds": round(elapsed, 4),
            "history_min": history_min,
            "history_avg": history_avg,
        }


def de_allocate(
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
    penalty_weight: float = 500.0,
    seed: int | None = None,
    warm_start: list[int] | None = None,
    **kwargs,
) -> tuple[list[TaskAllocation], list[str]]:
    """差分进化任务分配 — 与 hungarian/auction 同签名

    返回 (allocations, unassigned)。allocations 按每架 UAV 的执行顺序
    排列（按 uav_id 分组即得任务序列）；DE 编码覆盖全部任务，
    unassigned 恒为空。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks]

    solver = DiscreteDESolver(
        uavs=uavs,
        tasks=tasks,
        pop_size=pop_size,
        generations=generations,
        F_init=F_init,
        CR_init=CR_init,
        elite_guide_prob=elite_guide_prob,
        heuristic_ratio=heuristic_ratio,
        uav_max_ranges=uav_max_ranges,
        energy_per_meter=energy_per_meter,
        penalty_weight=penalty_weight,
        seed=seed,
        warm_start=warm_start,
    )
    allocation, _stats = solver.solve()

    allocations: list[TaskAllocation] = []
    for uav_idx, seq in allocation.items():
        costs = solver.compute_path_costs({uav_idx: seq})[uav_idx]
        uav = uavs[uav_idx]
        for k, task_idx in enumerate(seq):
            allocations.append(
                TaskAllocation(
                    uav_id=uav.id,
                    task_id=tasks[task_idx].id,
                    estimated_cost=costs[k],
                )
            )
    return allocations, []
