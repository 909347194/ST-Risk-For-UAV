"""补给(充电)energy 模块测试 — 数值基准取自设计文档 无人机补给分配设计.md §4"""

import numpy as np
import pytest

from src.domain.models import ChargingStation, Position
from src.algorithms.task_allocation.energy.feasibility import check_energy_feasibility
from src.algorithms.task_allocation.energy.plan import (
    ChargeEvent,
    RechargePlan,
    battery_levels,
)


def test_charging_station_valid():
    s = ChargingStation(id="C", position=Position(x=0, y=0), power=700.0)
    assert s.slots == 1


def test_charging_station_power_must_be_positive():
    with pytest.raises(Exception):
        ChargingStation(id="C", position=Position(x=0, y=0), power=0.0)


def test_recharge_plan_defaults():
    p = RechargePlan()
    assert p.uav_id == "" and p.charges == [] and p.feasible is True


def test_charge_event_fields():
    ev = ChargeEvent(station_id="C", charge_wh=70.0, arrive_time=70.0, leave_time=430.0)
    assert ev.charge_wh == 70.0 and ev.leave_time == 430.0


def test_battery_levels():
    assert battery_levels(100.0, 10.0) == pytest.approx(
        [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    )
    assert battery_levels(100.0, 300.0) == pytest.approx([0.0, 100.0])
    assert battery_levels(100.0, -1.0) == pytest.approx([0.0, 100.0])


# 节点: 0=D(起点), 1=T1, 2=T2, 3=T3, 4=E(终点), 5=C(充电站)
# 能耗 (Wh) 取自设计文档 §4.0 表; D→C=50 取自 §4.3
# 注: §4.0 表声明各弧对称, 却同时列出 C→T2=35 与 T2→C=40(自相矛盾);
# 因矩阵按对称构造, 后一行会覆盖前一行。按 §4.2/§4.3 演算(C→T2=35,
# 绕行 T1→C→T2 = 30+35 = 65)取 35, 故 {T2,C} 只保留一行。
_ENERGIES = [
    (0, 1, 40.0), (1, 2, 60.0), (2, 3, 30.0), (3, 4, 25.0),
    (0, 5, 50.0), (1, 5, 30.0), (5, 2, 35.0), (5, 3, 15.0),
]


def _e_matrix() -> np.ndarray:
    # 未列入 _ENERGIES 的弧视为不存在(inf), 不能把「无弧」读成 0 成本边:
    # §4.0 表无 C↔E 弧, 若默认 0, DP 会借 T3→C→E 免费绕行, 使 §4.4 的
    # 「充 60 终点电量 0 < σ → 被拒」失效(实测得 458.57s 而非 520s)。
    m = np.full((6, 6), np.inf)
    for i, j, w in _ENERGIES:
        m[i, j] = w
        m[j, i] = w
    return m


def test_check_energy_no_charge_infeasible():
    # §4.1: D→T1→T2→T3→E 直飞, 到 T2 电量 0 < σ
    ok, arrivals = check_energy_feasibility([0, 1, 2, 3, 4], _e_matrix(), B=100.0, sigma=10.0)
    assert ok is False
    assert arrivals == pytest.approx([100.0, 60.0, 0.0, -30.0, -55.0])


def test_check_energy_feasible_when_enough():
    ok, arrivals = check_energy_feasibility([0, 1], _e_matrix(), B=100.0, sigma=10.0)
    assert ok is True and arrivals == pytest.approx([100.0, 60.0])


def test_check_energy_sigma_defaults_to_10pct_battery():
    ok1, _ = check_energy_feasibility([0, 1, 2, 3, 4], _e_matrix(), B=100.0)
    ok2, _ = check_energy_feasibility([0, 1, 2, 3, 4], _e_matrix(), B=100.0, sigma=10.0)
    assert ok1 == ok2 == False


from src.algorithms.task_allocation.energy.greedy import greedy_insert_stations

_STATION = ChargingStation(id="C", position=Position(x=0, y=0), power=700.0)


def test_greedy_doc_example():
    # §4.2: 在 T1 触发, 绕行 C 充满 70, 总时间 520s
    plan = greedy_insert_stations(
        [0, 1, 2, 3, 4], _e_matrix(), [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is not None
    assert plan.node_seq == [0, 1, 5, 2, 3, 4]
    assert len(plan.charges) == 1
    c = plan.charges[0]
    assert c.station_id == "C"
    assert c.charge_wh == pytest.approx(70.0)
    assert c.arrive_time == pytest.approx(70.0)
    assert c.leave_time == pytest.approx(430.0)
    assert plan.total_time == pytest.approx(520.0)
    assert plan.total_energy == pytest.approx(160.0)
    assert plan.arrival_times == pytest.approx([0.0, 40.0, 70.0, 465.0, 495.0, 520.0])
    assert plan.feasible is True


def test_greedy_station_unreachable_returns_none():
    # 站离 T1 200Wh, 触发时电量 60 连站都到不了
    m = _e_matrix()
    m[1, 5] = m[5, 1] = 200.0
    plan = greedy_insert_stations(
        [0, 1, 2, 3, 4], m, [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is None


def test_greedy_no_charging_needed():
    # 短路线不触发充电 → 无充电事件的可行计划
    plan = greedy_insert_stations(
        [0, 1], _e_matrix(), [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is not None
    assert plan.charges == [] and plan.node_seq == [0, 1]
    assert plan.total_time == pytest.approx(40.0)


def test_greedy_charged_exit_leg_below_sigma_returns_none():
    # 站本身可达, 但充满后离站段 T1→C→T2 中 C→T2=95 > B−σ=90:
    # 到 T2 只剩 5 < σ, 插站救不了 → 必须返回 None, 不能给出 feasible=True 的假计划
    m = np.zeros((6, 6))
    m[0, 1] = m[1, 0] = 5.0
    m[1, 2] = m[2, 1] = 90.0
    m[1, 5] = m[5, 1] = 10.0
    m[5, 2] = m[2, 5] = 95.0
    plan = greedy_insert_stations(
        [0, 1, 2], m, [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is None


from src.algorithms.task_allocation.energy.dp import optimal_charging_dp


def test_dp_matches_greedy_on_single_station():
    # §4.3: 单站 + 带 σ 最优 = 充满, DP 与贪心一致 (520s)
    plan = optimal_charging_dp(
        [0, 1, 2, 3, 4], _e_matrix(), [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is not None
    assert plan.total_time == pytest.approx(520.0)
    assert len(plan.charges) == 1
    assert plan.charges[0].charge_wh == pytest.approx(70.0)
    assert plan.arrival_times == pytest.approx([0.0, 40.0, 70.0, 465.0, 495.0, 520.0])


def test_dp_rejects_partial_charge_violating_sigma():
    # §4.4: 充 60 的总时间 468.57s 更短, 但终点电量 0 < σ → 必须被拒
    plan = optimal_charging_dp(
        [0, 1, 2, 3, 4], _e_matrix(), [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is not None
    assert plan.total_time == pytest.approx(520.0)  # 而非 468.57
    assert plan.charges[0].charge_wh == pytest.approx(70.0)  # 而非 60


def test_dp_infeasible_returns_none():
    m = _e_matrix()
    m[1, 5] = m[5, 1] = 200.0  # 站不可达且直飞不可行
    plan = optimal_charging_dp(
        [0, 1, 2, 3, 4], m, [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is None


def test_dp_no_charging_needed():
    plan = optimal_charging_dp(
        [0, 1], _e_matrix(), [_STATION], [5],
        B=100.0, sigma=10.0, speed=10.0, energy_per_meter=0.1,
    )
    assert plan is not None
    assert plan.charges == [] and plan.total_time == pytest.approx(40.0)
