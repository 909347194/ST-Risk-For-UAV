"""补给(充电)energy 模块测试 — 数值基准取自设计文档 无人机补给分配设计.md §4"""

import pytest

from src.domain.models import ChargingStation, Position
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
