"""验证算法 API 可调用性 — 对运行中的服务发起真实 HTTP 请求"""

import sys
import httpx

BASE = "http://localhost:8000/api/v1"

UAVS = [
    {"id": "uav-1", "position": {"x": 0, "y": 0, "z": 10}, "speed": 15.0, "max_payload": 5.0, "battery": 200.0, "status": "idle"},
    {"id": "uav-2", "position": {"x": 50, "y": 0, "z": 10}, "speed": 12.0, "max_payload": 8.0, "battery": 300.0, "status": "idle"},
    {"id": "uav-3", "position": {"x": 100, "y": 20, "z": 10}, "speed": 10.0, "max_payload": 3.0, "battery": 150.0, "status": "idle"},
]

TASKS = [
    {"id": "task-1", "position": {"x": 20, "y": 30, "z": 0}, "priority": "high", "payload_weight": 1.0, "time_limit": 600.0},
    {"id": "task-2", "position": {"x": 80, "y": 60, "z": 0}, "priority": "medium", "payload_weight": 2.0},
    {"id": "task-3", "position": {"x": -10, "y": 70, "z": 0}, "priority": "low", "payload_weight": 0.5},
    {"id": "task-4", "position": {"x": 120, "y": 90, "z": 0}, "priority": "high", "payload_weight": 3.0, "time_limit": 900.0},
    {"id": "task-5", "position": {"x": 60, "y": 110, "z": 0}, "priority": "urgent", "payload_weight": 1.5, "time_limit": 300.0},
]

PLAN = {
    "uav_id": "uav-1",
    "task_id": "task-1",
    "start": {"x": 0, "y": 0, "z": 10},
    "goal": {"x": 100, "y": 80, "z": 0},
    "obstacles": [
        {"center": {"x": 40, "y": 40, "z": 0}, "radius": 8.0},
        {"center": {"x": 70, "y": 30, "z": 0}, "radius": 6.0},
    ],
    "speed": 12.0,
    "algorithm": "astar",
    "grid_resolution": 5.0,
    "bounds": {"x_min": -20, "x_max": 140, "y_min": -20, "y_max": 130},
}

failures = []


def check(name: str, resp: httpx.Response) -> None:
    ok = resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json")
    if ok:
        body = resp.json()
        # 分配接口应返回 allocations / algorithm_used 字段
        if name.startswith("allocate"):
            assert "allocations" in body and "algorithm_used" in body and body["algorithm_used"] == name.split("/")[-1]
            assert isinstance(body["allocations"], list) and all("uav_id" in a and "task_id" in a for a in body["allocations"])
        # 规划接口应返回 plan / algorithm_used 字段
        if name.startswith("plan"):
            assert "plan" in body and body["algorithm_used"] == name.split("/")[-1]
            assert body["plan"]["waypoints"] and body["plan"]["total_distance"] > 0
        status = "PASS"
        print(f"[PASS] {name}: {len(body.get('allocations', body.get('plan', {}).get('waypoints', [])))} 条结果")
    else:
        status = "FAIL"
        failures.append((name, resp.status_code, resp.text[:300]))
        print(f"[FAIL] {name}: HTTP {resp.status_code} -> {resp.text[:300]}")
    assert status == "PASS", f"{name} failed"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        # 1) 算法列表
        for path in ("/algorithms", "/tasks/algorithms", "/paths/algorithms"):
            r = client.get(path)
            ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0
            if ok:
                print(f"[PASS] GET {path}: {len(r.json())} 个算法")
            else:
                failures.append((path, r.status_code, r.text[:200]))
                print(f"[FAIL] GET {path}: HTTP {r.status_code} -> {r.text[:200]}")

        # 2) 任务分配 — 4 个算法
        for algo in ("hungarian", "auction", "de", "cw"):
            payload = {"uavs": UAVS, "tasks": TASKS, "algorithm": algo}
            r = client.post("/tasks/allocate", json=payload)
            check(f"allocate/{algo}", r)

        # 3) 任务分配 — 错误算法名应返回 400
        r = client.post("/tasks/allocate", json={"uavs": UAVS, "tasks": TASKS, "algorithm": "nonexistent"})
        if r.status_code == 400:
            print(f"[PASS] allocate/nonexistent: 400 {r.json().get('detail', '')[:80]}")
        else:
            failures.append(("allocate/nonexistent", r.status_code, r.text[:200]))
            print(f"[FAIL] allocate/nonexistent: HTTP {r.status_code}")

        # 4) 航线规划 — astar / rrt
        for algo in ("astar", "rrt"):
            payload = {**PLAN, "algorithm": algo}
            r = client.post("/paths/plan", json=payload)
            check(f"plan/{algo}", r)

    if failures:
        print(f"\n共 {len(failures)} 个用例失败")
        return 1
    print("\n全部用例通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
