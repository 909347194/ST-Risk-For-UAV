"""④ 任务分配 API 端点契约测试

算法层的参数校验抛 ValueError，端点必须把它映射为 400（客户端错误），
而不是让它逃逸成 500（服务端错误）。
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app

# 不抛出服务端异常，才能观察到真实的 500 响应而非测试框架的异常
client = TestClient(app, raise_server_exceptions=False)

URL = "/api/v1/tasks/allocate"


def _payload(algorithm: str, params: dict) -> dict:
    return {
        "uavs": [
            {"id": "uav-0", "position": {"x": 0.0, "y": 0.0}, "speed": 10.0,
             "max_payload": 5.0, "battery": 1000.0},
            {"id": "uav-1", "position": {"x": 100.0, "y": 0.0}, "speed": 10.0,
             "max_payload": 5.0, "battery": 1000.0},
        ],
        "tasks": [
            {"id": "task-0", "position": {"x": 10.0, "y": 0.0}, "payload_weight": 1.0},
            {"id": "task-1", "position": {"x": 90.0, "y": 0.0}, "payload_weight": 1.0},
        ],
        "algorithm": algorithm,
        "params": params,
    }


@pytest.mark.parametrize(
    ("algorithm", "params", "fragment"),
    [
        ("de", {"pop_size": 3}, "pop_size"),
        ("de", {"heuristic_ratio": 0.0}, "heuristic_ratio"),
        ("de", {"heuristic_ratio": 1.5}, "heuristic_ratio"),
        ("de", {"warm_start": [0]}, "warm_start"),          # 长度 ≠ 任务数
        ("de", {"warm_start": [0, 5]}, "warm_start"),       # 基因值越界
        ("de", {"uav_max_ranges": [100.0]}, "uav_max_ranges"),
        ("cw", {"uav_max_ranges": [100.0]}, "uav_max_ranges"),
        ("cw", {"uav_max_ranges": [0.0, 100.0]}, "uav_max_ranges"),
    ],
    ids=[
        "de-pop-size-too-small",
        "de-heuristic-ratio-zero",
        "de-heuristic-ratio-over-one",
        "de-warm-start-wrong-length",
        "de-warm-start-value-out-of-range",
        "de-uav-max-ranges-wrong-length",
        "cw-uav-max-ranges-wrong-length",
        "cw-uav-max-ranges-non-positive",
    ],
)
def test_invalid_algorithm_params_return_400(algorithm: str, params: dict, fragment: str):
    resp = client.post(URL, json=_payload(algorithm, params))

    assert resp.status_code == 400
    # 校验信息须回传给客户端，便于定位是哪个参数不合法
    assert fragment in resp.json()["detail"]


def test_valid_request_returns_200():
    """修复不能误伤正常请求"""
    resp = client.post(
        URL, json=_payload("de", {"seed": 0, "pop_size": 10, "generations": 5})
    )

    assert resp.status_code == 200
    assert resp.json()["algorithm_used"] == "de"


def test_unknown_algorithm_returns_400():
    """原有行为：未知算法名仍为 400"""
    resp = client.post(URL, json=_payload("nonexistent", {}))

    assert resp.status_code == 400
    assert "nonexistent" in resp.json()["detail"]
