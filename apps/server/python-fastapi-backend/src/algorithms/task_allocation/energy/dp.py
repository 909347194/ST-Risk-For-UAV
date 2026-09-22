"""策略 E — 离散充电量 DP 最优充电计划"""

from __future__ import annotations

from .plan import ChargeEvent, RechargePlan, battery_levels

# 状态值类型: (累计时间, (充电量, 站列表下标 | None))
_State = tuple[float, tuple[float, int | None]]


def _add(
    states: dict[float, _State],
    e: float,
    t: float,
    prev: tuple[float, int | None],
) -> None:
    cur = states.get(e)
    if cur is None or t < cur[0] - 1e-9:
        states[e] = (t, prev)


def _prune(states: dict[float, _State]) -> dict[float, _State]:
    """支配剪枝: 电量 ≥ 且时间 ≤ 的状态保留"""
    out: dict[float, _State] = {}
    best_t = float("inf")
    for e, (t, prev) in sorted(states.items(), key=lambda kv: -kv[0]):
        if t < best_t - 1e-9:
            out[e] = (t, prev)
            best_t = t
    return out


def optimal_charging_dp(seq, e_matrix, stations, station_indices, B, sigma, speed, energy_per_meter, delta=None):
    """给定任务序列的最优充电计划(充电量离散化 DP)

    seq[0] 为 UAV 起点;电量连续(飞行扣减),充电量只取离散档;
    终点要求到达电量 ≥ σ。无可行计划返回 None。
    """
    sigma = sigma if sigma is not None else 0.1 * B
    if len(seq) < 2:
        return RechargePlan(
            node_seq=list(seq), arrival_times=[0.0], total_time=0.0,
            total_energy=0.0, feasible=True,
        )
    if speed <= 0:
        return None
    levels = battery_levels(B, delta or B / 10.0)

    def fly_time(i: int, j: int) -> float:
        return float(e_matrix[i, j]) / energy_per_meter / speed

    def charge_time(wh: float, k: int) -> float:
        return wh * 3600.0 / stations[k].power

    n = len(seq)
    # layers[pos] = {电量: (最小累计时间, (充电量, 站下标|None))}
    layers: list[dict[float, _State]] = [dict() for _ in range(n)]
    layers[0][float(B)] = (0.0, (0.0, None))
    for pos in range(n - 1):
        i, nxt = seq[pos], seq[pos + 1]
        nxt_states: dict[float, _State] = {}
        for e, (t, _prev) in layers[pos].items():
            # 转移 1: 直飞
            if e - float(e_matrix[i, nxt]) >= sigma - 1e-9:
                _add(
                    nxt_states, e - float(e_matrix[i, nxt]),
                    t + fly_time(i, nxt), (0.0, None),
                )
            # 转移 2: 绕站 → 充至任意档 → 飞下一节点
            for k, s in enumerate(station_indices):
                e_at = e - float(e_matrix[i, s])
                if e_at < sigma - 1e-9:
                    continue
                for e2 in levels:
                    if e2 < e_at - 1e-9:
                        continue
                    e_arr = e2 - float(e_matrix[s, nxt])
                    if e_arr < sigma - 1e-9:
                        continue
                    q = e2 - e_at
                    tt = t + fly_time(i, s) + charge_time(q, k) + fly_time(s, nxt)
                    _add(nxt_states, e_arr, tt, (q, k))
        layers[pos + 1] = _prune(nxt_states)

    end = layers[n - 1]
    end_feasible = [(e, (t, prev)) for e, (t, prev) in end.items() if e >= sigma - 1e-9]
    if not end_feasible:
        return None
    e_end, (t_end, _prev) = min(end_feasible, key=lambda item: item[1][0])

    # 回溯: 逐位置取出 (充电量, 站下标) 决策
    decisions: list[tuple[float, int | None]] = []
    e = e_end
    for pos in range(n - 1, 0, -1):
        _t, (q, k) = layers[pos][e]
        decisions.append((q, k))
        i = seq[pos - 1]
        if k is not None:
            s = station_indices[k]
            e = e + float(e_matrix[s, seq[pos]]) - q + float(e_matrix[i, s])
        else:
            e = e + float(e_matrix[i, seq[pos]])
    decisions.reverse()

    # 前向重建节点序列 / 充电事件 / 到达时刻
    node_seq: list[int] = [seq[0]]
    arrival_times: list[float] = [0.0]
    charges: list[ChargeEvent] = []
    t_acc = 0.0
    for pos in range(1, n):
        q, k = decisions[pos - 1]
        i = seq[pos - 1]
        if k is not None:
            s = station_indices[k]
            t_acc += fly_time(i, s)
            node_seq.append(s)
            arrival_times.append(t_acc)
            arrive = t_acc
            t_acc += charge_time(q, k)
            charges.append(
                ChargeEvent(
                    station_id=stations[k].id,
                    charge_wh=q,
                    arrive_time=arrive,
                    leave_time=t_acc,
                )
            )
            t_acc += fly_time(s, seq[pos])
        else:
            t_acc += fly_time(i, seq[pos])
        node_seq.append(seq[pos])
        arrival_times.append(t_acc)

    total_energy = float(
        sum(e_matrix[node_seq[p], node_seq[p + 1]] for p in range(len(node_seq) - 1))
    )
    return RechargePlan(
        node_seq=node_seq,
        charges=charges,
        total_time=t_acc,
        total_energy=total_energy,
        arrival_times=arrival_times,
        feasible=True,
    )
