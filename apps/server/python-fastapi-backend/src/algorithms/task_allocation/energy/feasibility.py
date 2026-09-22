"""能量可行性 — 逐段 SoC 跟踪(不插站)"""


def check_energy_feasibility(
    seq: list[int],
    e_matrix,
    B: float,
    sigma: float | None = None,
) -> tuple[bool, list[float]]:
    """逐段电量扣减:返回 (可行?, 逐节点到达电量)

    seq[0] 为 UAV 起点(满电 B 出发),其余为任务节点矩阵下标。
    可行 = 每个节点(含终点)到达电量 ≥ σ;σ=None 时按 0.1×B 推导。
    """
    sigma = sigma if sigma is not None else 0.1 * B
    e = B
    arrivals: list[float] = [float(e)]
    for prev, nxt in zip(seq, seq[1:]):
        e -= float(e_matrix[prev, nxt])
        arrivals.append(float(e))
    return all(a >= sigma - 1e-9 for a in arrivals), arrivals
