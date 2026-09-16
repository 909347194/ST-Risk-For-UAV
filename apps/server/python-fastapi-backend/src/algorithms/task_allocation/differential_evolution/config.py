"""DE 求解器配置与常量 — 超参数单一来源，魔法数字集中命名"""

from dataclasses import dataclass

# ———— 惩罚与行为常量（原散落在各方法中的魔法数字）————
RANGE_PENALTY = 10000.0            # 基础适应度中超航程的固定惩罚
DEADLINE_VIOLATION_PENALTY = 0.5   # 单个任务 deadline 违反的惩罚增量
LOAD_BALANCE_WEIGHT = 0.01         # 负载均衡方差惩罚系数
FLIP_PROBABILITY = 0.1             # 启发式/扰动初始化中基因随机翻转比例
F_DECAY = 0.6                      # F 随进化进度衰减幅度（0.9 → 0.36）
CR_GROWTH = 0.4                    # CR 随进化进度增长幅度（0.5 → 0.9）


@dataclass(frozen=True)
class DEConfig:
    """DE 超参数集合 — 默认值与 DiscreteDESolver 构造器保持一致

    单一来源：构造器 / de_allocate / 注册表 params_schema 均以本类字段为准。
    """

    pop_size: int = 50
    generations: int = 100
    F_init: float = 0.9
    CR_init: float = 0.5
    elite_guide_prob: float = 0.3
    heuristic_ratio: float = 0.2
    energy_per_meter: float = 0.1
    alpha: float = 1.0
    beta: float = 0.5
    gamma: float = 1.0
    penalty_weight: float = 500.0
    seed: int | None = None
    warm_start: list[int] | None = None

    def validate(self, n_task: int, n_uav: int) -> None:
        """参数校验 — 无效值提前以清晰错误拒绝，而非在进化中途崩溃

        n_task / n_uav 用于 warm_start 的长度与值域校验。
        """
        if self.pop_size < 4:
            raise ValueError(f"pop_size 必须 >= 4（变异需 3 个互异候选个体），当前: {self.pop_size}")
        if not 0.0 < self.heuristic_ratio <= 1.0:
            raise ValueError(f"heuristic_ratio 必须在 (0, 1] 区间，当前: {self.heuristic_ratio}")

        # warm_start 校验: 长度与值域
        if self.warm_start is not None:
            if len(self.warm_start) != n_task:
                raise ValueError(
                    f"warm_start 长度必须等于任务数 ({n_task})，当前: {len(self.warm_start)}"
                )
            if any(not 0 <= g < n_uav for g in self.warm_start):
                raise ValueError(f"warm_start 基因值必须在 [0, {n_uav}) 区间")
