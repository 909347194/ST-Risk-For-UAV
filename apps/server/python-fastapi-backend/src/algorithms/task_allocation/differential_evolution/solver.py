"""离散差分进化求解器 — 组装 config / encoding / population / operators / fitness 并驱动主循环"""

import time

import numpy as np

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
)

from . import encoding, fitness, operators, population
from .config import DEConfig


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

        # 超参集中到 config — 构造器参数即 DEConfig 字段，单一来源
        self.config = DEConfig(
            pop_size=pop_size,
            generations=generations,
            F_init=F_init,
            CR_init=CR_init,
            elite_guide_prob=elite_guide_prob,
            heuristic_ratio=heuristic_ratio,
            energy_per_meter=energy_per_meter,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            penalty_weight=penalty_weight,
            seed=seed,
            warm_start=warm_start,
        )
        # 兼容属性 — 保持与旧版一致的访问方式
        self.pop_size = self.config.pop_size
        self.gens = self.config.generations
        self.F_init = self.config.F_init
        self.CR_init = self.config.CR_init
        self.elite_guide_prob = self.config.elite_guide_prob
        self.heuristic_ratio = self.config.heuristic_ratio
        self.alpha = self.config.alpha
        self.beta = self.config.beta
        self.gamma = self.config.gamma
        self.penalty_weight = self.config.penalty_weight
        self.rng = np.random.default_rng(self.config.seed)

        # 参数校验 — 无效值提前以清晰错误拒绝，而非在进化中途崩溃
        self.config.validate(self.N_task, self.N_uav)

        self.warm_start = self.config.warm_start

        # 最大航程: 显式参数优先, 否则按电池/能耗率推算（校验在公共函数内）
        self.uav_max_ranges = derive_uav_ranges(uavs, uav_max_ranges, self.config.energy_per_meter)

        self._build_cost_matrix()

    # ———— 代价矩阵 ————
    def _build_cost_matrix(self) -> None:
        self.cost_matrix = build_cost_matrix(self.uavs, self.tasks)

    # ———— 编码 / 解码 ————
    def encode(self, uav_task_dict: dict[int, list[int]]) -> list[int]:
        """分配方案 → 整数个体（与 decode 互逆）

        输入: {uav_id: [task_id, ...]}（如 ClarkeWright 的 routes / 任意可行分配）
        输出: [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]
        """
        return encoding.encode_assignment(uav_task_dict, self.N_task)

    # ———— 解码 ————
    def decode(self, individual: list[int] | np.ndarray) -> dict[int, list[int]]:
        """整数编码 → {uav_id: [task_id, ...]} (最近邻排序)

        个体: [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]
        """
        return encoding.decode(self.cost_matrix, self.N_uav, self.N_task, individual)

    # ———— 路径代价 ————
    def compute_path_costs(
        self, uav_task_dict: dict[int, list[int]]
    ) -> dict[int, list[float]]:
        """计算每架 UAV 任务序列的逐段代价"""
        return encoding.compute_path_costs(self.cost_matrix, self.N_uav, self.N_task, uav_task_dict)

    # ———— 自适应参数 ————
    def _adaptive_params(self, gen: int) -> tuple[float, float]:
        return operators.adaptive_params(gen, self.gens, self.F_init, self.CR_init)

    # ———— 启发式初始化 ————
    def _init_population(self) -> np.ndarray:
        return population.init_population(
            self.cost_matrix,
            self.N_uav,
            self.N_task,
            self.pop_size,
            self.heuristic_ratio,
            self.rng,
            self.warm_start,
        )

    # ———— 精英引导变异 ————
    def _mutate(
        self,
        population: np.ndarray,
        idx: int,
        best_idx: int,
        gen: int,
    ) -> np.ndarray:
        return operators.mutate(
            population,
            idx,
            best_idx,
            gen,
            self.rng,
            self.pop_size,
            self.elite_guide_prob,
            self.F_init,
            self.CR_init,
            self.gens,
        )

    # ———— 二项式交叉 ————
    def _crossover(
        self,
        target: np.ndarray,
        mutant: np.ndarray,
        gen: int,
    ) -> np.ndarray:
        return operators.crossover(target, mutant, gen, self.rng, self.N_task, self.CR_init, self.gens)

    # ———— 修复 ————
    def _repair(self, individual: np.ndarray) -> np.ndarray:
        """取整 → 钳位"""
        return operators.repair(individual, self.N_uav)

    # ———— 基础适应度 ————
    def evaluate(self, individual: list[int]) -> float:
        """基础适应度 = 总路径代价 + 超航程惩罚"""
        return fitness.evaluate(
            self.cost_matrix, self.N_uav, self.N_task, self.uav_max_ranges, individual
        )

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
        return fitness.evaluate_constrained(
            self.cost_matrix,
            self.N_uav,
            self.N_task,
            self.uavs,
            self.tasks,
            self.uav_max_ranges,
            individual,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            penalty_weight=penalty_weight,
        )

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
