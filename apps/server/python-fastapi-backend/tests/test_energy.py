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
_ENERGIES = [
    (0, 1, 40.0), (1, 2, 60.0), (2, 3, 30.0), (3, 4, 25.0),
    (0, 5, 50.0), (1, 5, 30.0), (5, 2, 35.0), (2, 5, 40.0), (5, 3, 15.0),
]


def _e_matrix() -> np.ndarray:
    m = np.zeros((6, 6))
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
