"""种群初始化 — 随机 / 贪心启发式 / 热启动"""

from __future__ import annotations

import numpy as np

from .config import FLIP_PROBABILITY


def greedy_individual(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
) -> np.ndarray:
    """贪心构造：每任务取代价最小的 UAV（列 argmin）"""
    ind = np.zeros(n_task, dtype=int)
    for tid in range(n_task):
        best_uav = int(np.argmin(cost_matrix[: n_uav, n_uav + tid]))
        ind[tid] = best_uav
    return ind


def perturb(
    individual: np.ndarray,
    rng: np.random.Generator,
    n_uav: int,
    flip_prob: float = FLIP_PROBABILITY,
) -> np.ndarray:
    """按比例随机翻转基因（保持为整数个体）"""
    ind = individual.copy()
    flip_mask = rng.random(len(ind)) < flip_prob
    ind[flip_mask] = rng.integers(0, n_uav, size=int(flip_mask.sum()))
    return ind


def random_individuals(
    n: int,
    n_uav: int,
    n_task: int,
    rng: np.random.Generator,
) -> list[np.ndarray]:
    """n 个均匀随机整数个体"""
    return [rng.integers(0, n_uav, size=n_task) for _ in range(n)]


def init_population(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    pop_size: int,
    heuristic_ratio: float,
    rng: np.random.Generator,
    warm_start: list[int] | None = None,
) -> np.ndarray:
    """构造初始种群 — 热启动优先，否则贪心扰动 + 随机个体"""
    if warm_start is not None:
        return init_population_with_warm_start(
            cost_matrix, n_uav, n_task, pop_size, heuristic_ratio, rng, warm_start
        )

    n_heuristic = max(1, int(pop_size * heuristic_ratio))
    n_random = pop_size - n_heuristic
    pop: list[np.ndarray] = []

    # 贪心构造 + 扰动
    for _ in range(n_heuristic):
        ind = greedy_individual(cost_matrix, n_uav, n_task)
        pop.append(perturb(ind, rng, n_uav))

    # 随机个体
    pop.extend(random_individuals(n_random, n_uav, n_task, rng))
    return np.array(pop)


def init_population_with_warm_start(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    pop_size: int,
    heuristic_ratio: float,
    rng: np.random.Generator,
    warm_start: list[int],
) -> np.ndarray:
    """热启动初始化 — 种群[0] = warm_start；其余 heuristic_ratio 比例为扰动个体，剩余随机"""
    pop: list[np.ndarray] = [np.array(warm_start, dtype=int)]
    n_perturbed = max(0, int((pop_size - 1) * heuristic_ratio))
    n_random = pop_size - 1 - n_perturbed
    base = np.array(warm_start, dtype=int)
    for _ in range(n_perturbed):
        pop.append(perturb(base, rng, n_uav))
    pop.extend(random_individuals(n_random, n_uav, n_task, rng))
    return np.array(pop)
