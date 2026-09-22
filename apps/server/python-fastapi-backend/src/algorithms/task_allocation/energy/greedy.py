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
            # 选绕行能耗最小的站, 并列时功率大者优先
            best_k: int | None = None
            best_detour = float("inf")
            for k, s in enumerate(station_indices):
                detour = float(e_matrix[i, s] + e_matrix[s, nxt])
                if best_k is None or detour < best_detour - 1e-9 or (
                    abs(detour - best_detour) <= 1e-9
                    and stations[k].power > stations[best_k].power
                ):
                    best_k, best_detour = k, detour
            if best_k is None:
                return None
            s = station_indices[best_k]
            if e - float(e_matrix[i, s]) < sigma - 1e-9:
                return None  # 连站都够不到
            # 飞往站
            t += fly_time(i, s)
            total_energy += float(e_matrix[i, s])
            e -= float(e_matrix[i, s])
            arrive = t
            # 充满
            q = B - e
            t += q * 3600.0 / stations[best_k].power
            node_seq.append(s)
            arrival_times.append(arrive)
            charges.append(
                ChargeEvent(
                    station_id=stations[best_k].id,
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
