"""DE 进化算子 — 自适应 F/CR、变异、交叉、修复（纯函数，rng 由调用方传入）"""

from __future__ import annotations

import numpy as np

from .config import F_DECAY, CR_GROWTH


def adaptive_params(
    gen: int,
    generations: int,
    F_init: float,
    CR_init: float,
) -> tuple[float, float]:
    """自适应 F/CR: F↓ (探索→开发), CR↑"""
    progress = gen / max(generations - 1, 1)
    F = F_init * (1.0 - F_DECAY * progress)   # 0.9 → 0.36
    CR = CR_init + CR_GROWTH * progress        # 0.5 → 0.9
    return F, CR


def mutate(
    population: np.ndarray,
    idx: int,
    best_idx: int,
    gen: int,
    rng: np.random.Generator,
    pop_size: int,
    elite_guide_prob: float,
    F_init: float,
    CR_init: float,
    generations: int,
) -> np.ndarray:
    """精英引导变异 — DE/current-to-best/1，否则 DE/rand/1（连续空间）"""
    F, _ = adaptive_params(gen, generations, F_init, CR_init)
    candidates = [i for i in range(pop_size) if i != idx]

    if rng.random() < elite_guide_prob and best_idx != idx:
        # DE/current-to-best/1
        r1, r2 = population[
            rng.choice(candidates, 2, replace=False)
        ]
        mutant = (
            population[idx].astype(float)
            + F * (population[best_idx].astype(float) - population[idx].astype(float))
            + F * (r1.astype(float) - r2.astype(float))
        )
    else:
        # DE/rand/1
        r1, r2, r3 = population[
            rng.choice(candidates, 3, replace=False)
        ]
        mutant = r1.astype(float) + F * (r2.astype(float) - r3.astype(float))

    return mutant


def crossover(
    target: np.ndarray,
    mutant: np.ndarray,
    gen: int,
    rng: np.random.Generator,
    n_task: int,
    CR_init: float,
    generations: int,
) -> np.ndarray:
    """二项式交叉 — j_rand 保证至少继承一个变异基因（连续空间）"""
    _, CR = adaptive_params(gen, generations, 0.0, CR_init)  # 仅用 CR，F 无需参与
    trial = target.astype(float)
    j_rand = int(rng.integers(n_task))
    rand = rng.random(n_task)
    for j in range(n_task):
        if rand[j] < CR or j == j_rand:
            trial[j] = mutant[j]
    return trial


def repair(individual: np.ndarray, n_uav: int) -> np.ndarray:
    """取整 → 钳位，修复回合法整数基因型"""
    return np.clip(np.round(individual).astype(int), 0, n_uav - 1)
