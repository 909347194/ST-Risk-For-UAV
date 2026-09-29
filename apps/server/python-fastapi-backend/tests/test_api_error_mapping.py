"""客户端输入错误必须映射为 4xx，不能冒泡成 500

端点在 HTTP 边界上把非法输入转成 400；任何未捕获的 ValueError /
KeyError / TypeError 都会变成 500，让调用方误以为服务端故障。
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app

# 不抛出服务端异常，才能观察到真实的 500 响应
client = TestClient(app, raise_server_exceptions=False)

B = "/api/v1"

FULL_BOUNDS = {"x_min": -10.0, "x_max": 100.0, "y_min": -10.0, "y_max": 100.0}


def _plan_payload(**overrides) -> dict:
    payload = {
        "uav_id": "uav-0",
        "task_id": "task-0",
        "start": {"x": 0.0, "y": 0.0},
        "goal": {"x": 50.0, "y": 50.0},
        "obstacles": [],
        "speed": 10.0,
        "algorithm": "astar",
    }
    payload.update(overrides)
    return payload


# ── GET /uavs?status= ──────────────────────────────────────────

@pytest.mark.parametrize("status", ["bogus", "BOGUS", "IDLE", "idle "])
def test_invalid_uav_status_returns_400(status: str):
    """枚举转换失败是客户端错误，不是服务端故障"""
    resp = client.get(f"{B}/uavs", params={"status": status})

    assert resp.status_code == 400
    assert status in resp.json()["detail"]


def test_valid_uav_status_returns_200():
    """修复不能误伤合法筛选"""
    resp = client.get(f"{B}/uavs", params={"status": "idle"})

    assert resp.status_code == 200


def test_absent_uav_status_returns_200():
    """不传 status 列出全部"""
    resp = client.get(f"{B}/uavs")

    assert resp.status_code == 200


# ── POST /paths/plan 的 bounds ─────────────────────────────────

@pytest.mark.parametrize("algorithm", ["astar", "rrt"])
@pytest.mark.parametrize(
    "bounds",
    [
        {"x_min": -10.0},                                 # 缺 3 个键
        {"x_min": -10.0, "y_min": -10.0, "y_max": 100.0},  # 缺 x_max
    ],
    ids=["only-x-min", "missing-x-max"],
)
def test_plan_bounds_missing_keys_returns_400(algorithm: str, bounds: dict):
    resp = client.post(f"{B}/paths/plan", json=_plan_payload(algorithm=algorithm, bounds=bounds))

    assert resp.status_code == 400
    assert "bounds" in resp.json()["detail"]


@pytest.mark.parametrize("algorithm", ["astar", "rrt"])
@pytest.mark.parametrize("bad_value", ["abc", None], ids=["str", "none"])
def test_plan_bounds_non_numeric_returns_400(algorithm: str, bad_value):
    resp = client.post(
        f"{B}/paths/plan",
        json=_plan_payload(algorithm=algorithm, bounds={**FULL_BOUNDS, "x_max": bad_value}),
    )

    assert resp.status_code == 400
    assert "bounds" in resp.json()["detail"]


def test_plan_with_full_bounds_returns_200():
    """修复不能误伤合法 bounds"""
    resp = client.post(f"{B}/paths/plan", json=_plan_payload(bounds=FULL_BOUNDS))

    assert resp.status_code == 200


def test_plan_without_bounds_returns_200():
    """不传 bounds 走默认边界（margin 50）"""
    resp = client.post(f"{B}/paths/plan", json=_plan_payload())

    assert resp.status_code == 200


def test_plan_unknown_algorithm_returns_400():
    """原有行为：未知算法名仍为 400"""
    resp = client.post(f"{B}/paths/plan", json=_plan_payload(algorithm="nope"))

    assert resp.status_code == 400
    assert "nope" in resp.json()["detail"]
