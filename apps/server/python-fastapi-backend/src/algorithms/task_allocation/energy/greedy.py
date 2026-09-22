"""策略 A — 阈值触发 + 绕行最小站 + 充满"""

from __future__ import annotations

from .plan import ChargeEvent, RechargePlan


def greedy_insert_stations(seq, e_matrix, stations, station_indices, B, sigma, speed, energy_per_meter):
    """贪心插站:到达下一节点后电量 < σ 时,插入绕行能耗最小的站并充满。

    注:上游设计文档 §6.3 伪代码在插站后仍按 c(prev, nxt) 扣减,
    这里按正确语义改为两段式 prev→s、s→nxt。
    """
    sigma = sigma if sigma is not None else 0.1 * B
    if speed <= 0:
        return None

    def fly_time(i: int, j: int) -> float:
        return float(e_matrix[i, j]) / energy_per_meter / speed

    node_seq: list[int] = [seq[0]]
    arrival_times: list[float] = [0.0]
    charges: list[ChargeEvent] = []
    e = B
    t = 0.0
    total_energy = 0.0
    i = seq[0]
    for nxt in seq[1:]:
        if e - float(e_matrix[i, nxt]) < sigma:
            # 候选站按绕行能耗升序, 并列时功率大者优先; 依次尝试, 取第一个
            # 同时通过到达检查(到站电量 ≥ σ)与充满后离站段复检(≥ σ)的站
            candidates = sorted(
                enumerate(station_indices),
                key=lambda ks: (
                    float(e_matrix[i, ks[1]] + e_matrix[ks[1], nxt]),
                    -stations[ks[0]].power,
                ),
            )
            chosen: tuple[int, int] | None = None
            for k, s in candidates:
                if e - float(e_matrix[i, s]) < sigma - 1e-9:
                    continue  # 连站都够不到 → 试下一站
                if B - float(e_matrix[s, nxt]) < sigma:
                    continue  # 充满后离站段仍不满足 σ(含 m[s,nxt] > B)→ 试下一站
                chosen = (k, s)
                break
            if chosen is None:
                return None  # 所有站都救不了
            k, s = chosen
            # 飞往站
            t += fly_time(i, s)
            total_energy += float(e_matrix[i, s])
            e -= float(e_matrix[i, s])
            arrive = t
            # 充满
            q = B - e
            t += q * 3600.0 / stations[k].power
            node_seq.append(s)
            arrival_times.append(arrive)
            charges.append(
                ChargeEvent(
                    station_id=stations[k].id,
                    charge_wh=q,
                    arrive_time=arrive,
                    leave_time=t,
                )
            )
            e = B
            i = s
        # 飞往下一节点
        t += fly_time(i, nxt)
        total_energy += float(e_matrix[i, nxt])
        e -= float(e_matrix[i, nxt])
        node_seq.append(nxt)
        arrival_times.append(t)
        i = nxt
    return RechargePlan(
        node_seq=node_seq,
        charges=charges,
        total_time=t,
        total_energy=total_energy,
        arrival_times=arrival_times,
        feasible=True,
    )
