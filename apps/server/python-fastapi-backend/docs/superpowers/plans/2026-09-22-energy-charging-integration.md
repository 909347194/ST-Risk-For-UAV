# 补给(充电)能量模块全链路接入 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在任务分配求解器(CW/DE)中接入充电站能量约束:新增 energy 内层模块(贪心 A + DP E),使分配结果附带充电计划,API 输出 `recharge_plans`。

**Architecture:** 外层分配 + 内层充电分层:energy 模块消费"每机任务序列 + 能耗矩阵",返回带充电计划的路线代价;C 在合并判定与构造后修复中嵌入能量检查,DE 在适应度中用 DP 真实时间(含充电)替换路径代价。stations 缺省时整体走现状路径。

**Tech Stack:** Python ≥ 3.12、numpy、pydantic v2、pytest(经 `uv run pytest`)。

**Spec:** `docs/superpowers/specs/2026-09-22-energy-charging-integration-design.md`(本目录上级 `specs/`)
**基准演算:** `docs/architecture/algorithms/task-allocation/无人机补给分配设计.md` §4(所有测试数值取自该节)

## Global Constraints

- 工作目录:`apps/server/python-fastapi-backend`;所有命令先 `cd` 到此目录。
- 测试命令:`uv run pytest tests/<file>.py::<test> -v`(不要用 `uv run test` 入口,该入口在当前环境不可用)。
- 向后兼容:stations 缺省(空列表)时行为与输出内容**完全不变**;既有测试仅 cw/de 入口直接解包处做 2→3 机械修改(清单见 Task 6/7),其余测试一律不得改动。
- 领域模型直接用于 schema(与 uavs/tasks 一致),**不**新建 `ChargingStationIn`。
- 单位约定:能耗 Wh、时间 s;能耗矩阵 = 纯距离 × `energy_per_meter`(不含优先级权重)。
- σ 缺省 = `0.1 × B`,推导发生在 energy 函数内部(调用方传 None 即可)。
- energy 层启用条件:`stations` 非空 **且** `energy_strategy != "none"`。
- 提交信息风格:`feat(python-api): …` / `test(python-api): …` / `refactor(python-api): …`。
- 每个 Task 的提交只包含本 Task 的文件,不要混入其他文件(注意 `scripts/` 目录目前是未跟踪状态,勿提交)。

---

### Task 1: ChargingStation 模型 + RechargePlan 数据类

**Files:**
- Create: `src/algorithms/task_allocation/energy/__init__.py`
- Create: `src/algorithms/task_allocation/energy/plan.py`
- Modify: `src/domain/models.py`(在 `Obstacle` 类之后追加)
- Test: `tests/test_energy.py`(新建,先只放本 Task 用例)

**Interfaces:**
- Consumes: 无(纯新代码)
- Produces(后续任务依赖):
  - `src.domain.models.ChargingStation`: `id: str`, `position: Position`, `power: float (gt=0)`, `slots: int = 1 (ge=1)`
  - `energy.plan.ChargeEvent`: `station_id: str`, `charge_wh: float`, `arrive_time: float`, `leave_time: float`
  - `energy.plan.RechargePlan`: `uav_id: str = ""`, `node_seq: list[int]`, `charges: list[ChargeEvent]`, `total_time: float`, `total_energy: float`, `arrival_times: list[float]`(与 node_seq 对齐), `feasible: bool = True`
  - `energy.plan.battery_levels(B, delta) -> list[float]`:[0, …, B] 含端点;delta 无效时退化为 [0.0, B]

- [ ] **Step 1: 写失败测试** — 追加到 `tests/test_energy.py`:

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_energy.py -v`
Expected: FAIL(import 错误 / ChargingStation 不存在)

- [ ] **Step 3: 写实现**

`src/domain/models.py` 中 `Obstacle` 类之后追加:

```python
class ChargingStation(BaseModel):
    """充电站"""
    id: str
    position: Position
    power: float = Field(gt=0, description="充电功率 (W)")
    slots: int = Field(default=1, ge=1, description="同时可服务无人机数")
```

`src/algorithms/task_allocation/energy/plan.py`:

```python
"""补给计划数据类与电量档工具"""

from dataclasses import dataclass, field


@dataclass
class ChargeEvent:
    """一次充电事件"""
    station_id: str
    charge_wh: float          # 充电量 (Wh)
    arrive_time: float        # 到站时刻 (s)
    leave_time: float         # 离站时刻 (s)


@dataclass
class RechargePlan:
    """一条路线的补给计划(节点序列 + 充电事件 + 代价)"""
    uav_id: str = ""
    node_seq: list[int] = field(default_factory=list)       # 扩展节点序列(矩阵索引)
    charges: list[ChargeEvent] = field(default_factory=list)
    total_time: float = 0.0        # 飞行 + 充电总时间 (s)
    total_energy: float = 0.0      # 总飞行能耗 (Wh)
    arrival_times: list[float] = field(default_factory=list)  # 与 node_seq 对齐
    feasible: bool = True


def battery_levels(B: float, delta: float) -> list[float]:
    """电量离散档 [0, ..., B](含端点);delta 无效时退化为 {0, B}"""
    if delta <= 0 or delta > B:
        return [0.0, B]
    levels: list[float] = []
    v = 0.0
    while v < B - 1e-9:
        levels.append(v)
        v += delta
    levels.append(B)
    return levels
```

`src/algorithms/task_allocation/energy/__init__.py`:

```python
"""内层补给模块 — 给定任务序列,计算充电计划与真实代价"""

from .plan import ChargeEvent, RechargePlan, battery_levels
from .feasibility import check_energy_feasibility
from .greedy import greedy_insert_stations
from .dp import optimal_charging_dp

__all__ = [
    "ChargeEvent",
    "RechargePlan",
    "battery_levels",
    "check_energy_feasibility",
    "greedy_insert_stations",
    "optimal_charging_dp",
]
```

> 注:此文件 import 了 Task 3-5 才创建的 `feasibility` / `greedy` / `dp`。为让本 Task 测试可运行,先创建这三个文件的占位版本(只含函数签名,函数体 `raise NotImplementedError`),Task 3-5 再逐一替换为真实实现。占位内容:

```python
# feasibility.py(占位)
def check_energy_feasibility(seq, e_matrix, B, sigma=None):
    raise NotImplementedError

# greedy.py(占位)
def greedy_insert_stations(seq, e_matrix, stations, station_indices, B, sigma, speed, energy_per_meter):
    raise NotImplementedError

# dp.py(占位)
def optimal_charging_dp(seq, e_matrix, stations, station_indices, B, sigma, speed, energy_per_meter, delta=None):
    raise NotImplementedError
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_energy.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add src/domain/models.py src/algorithms/task_allocation/energy tests/test_energy.py
git commit -m "feat(python-api): 新增 ChargingStation 模型与补给计划数据类"
```

---

### Task 2: 距离 / 能耗矩阵扩展

**Files:**
- Modify: `src/algorithms/task_allocation/_common.py`(文件末尾追加两个函数)
- Test: `tests/test_task_allocation.py`(追加用例)与 `tests/test_energy.py`

**Interfaces:**
- Consumes: `src.utils.utils.distance(a, b) -> float`
- Produces:
  - `build_distance_matrix(uavs, tasks, stations=None) -> np.ndarray`:纯物理距离矩阵,索引约定 `0..N_uav-1` = UAV,`N_uav..N_uav+N_task-1` = 任务,其后 = 充电站;对角 0
  - `build_energy_matrix(uavs, tasks, stations=None, energy_per_meter=0.1) -> np.ndarray`:`distance_matrix × energy_per_meter`

- [ ] **Step 1: 写失败测试** — `tests/test_task_allocation.py` 末尾追加:

```python
# ── 距离 / 能耗矩阵 ──

def test_build_distance_matrix_includes_stations():
    from src.algorithms.task_allocation._common import (
        build_distance_matrix,
        build_energy_matrix,
    )

    uavs = [_de_uav(0, 0, "uav-0")]
    tasks = [_de_task(3, 4, "task-0")]
    stations = [ChargingStation(id="S", position=Position(x=0, y=4, z=0), power=700.0)]
    d = build_distance_matrix(uavs, tasks, stations)
    assert d.shape == (3, 3)
    assert d[0, 1] == pytest.approx(5.0)     # uav→task
    assert d[0, 2] == pytest.approx(4.0)     # uav→station
    assert d[1, 2] == pytest.approx(3.0)     # task→station
    assert d[1, 0] == pytest.approx(5.0)     # 对称
    e = build_energy_matrix(uavs, tasks, stations, energy_per_meter=0.1)
    assert e[0, 1] == pytest.approx(0.5)
    # 不带站时与旧行为一致(不含权重)
    d2 = build_distance_matrix(uavs, tasks)
    assert d2.shape == (2, 2) and d2[0, 1] == pytest.approx(5.0)
```

同时在该文件顶部 import 区补充 `from src.domain.models import ChargingStation`(若已存在则跳过)。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_build_distance_matrix_includes_stations -v`
Expected: FAIL(`build_distance_matrix` 不存在)

- [ ] **Step 3: 写实现** — `_common.py` 末尾追加:

```python
def build_distance_matrix(
    uavs: list[UAV],
    tasks: list[Task],
    stations: list | None = None,
) -> np.ndarray:
    """(N_uav+N_task+N_s)×同尺寸 纯物理距离矩阵(无优先级权重)

    索引约定: 0..N_uav-1 为 UAV，N_uav..N_uav+N_task-1 为任务，其后为充电站。
    """
    stations = stations or []
    points = [u.position for u in uavs] + [t.position for t in tasks] + [s.position for s in stations]
    n = len(points)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            matrix[i, j] = distance(points[i], points[j])
    return matrix


def build_energy_matrix(
    uavs: list[UAV],
    tasks: list[Task],
    stations: list | None = None,
    energy_per_meter: float = 0.1,
) -> np.ndarray:
    """能耗矩阵 (Wh) = 纯距离 × energy_per_meter，供能量层使用"""
    return build_distance_matrix(uavs, tasks, stations) * energy_per_meter
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_task_allocation.py::test_build_distance_matrix_includes_stations -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/algorithms/task_allocation/_common.py tests/test_task_allocation.py
git commit -m "feat(python-api): 新增距离/能耗矩阵构造(含充电站节点)"
```

---

### Task 3: check_energy_feasibility — 逐段 SoC 检查

**Files:**
- Modify: `src/algorithms/task_allocation/energy/feasibility.py`(替换占位)
- Test: `tests/test_energy.py`(追加)

**Interfaces:**
- Consumes: `battery_levels` 之外的 Task 1 产出;输入 `seq` 首元素为 UAV 起点矩阵下标
- Produces: `check_energy_feasibility(seq, e_matrix, B, sigma=None) -> tuple[bool, list[float]]` — 返回 `(全部到达电量 ≥ σ?, 逐节点到达电量列表)`;`sigma=None` 时内部按 `0.1 × B` 推导

- [ ] **Step 1: 写失败测试** — `tests/test_energy.py` 追加:

```python
import numpy as np

from src.algorithms.task_allocation.energy.feasibility import check_energy_feasibility

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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_energy.py -k check_energy -v`
Expected: FAIL(NotImplementedError)

- [ ] **Step 3: 写实现** — 替换 `feasibility.py` 占位:

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_energy.py -k check_energy -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/algorithms/task_allocation/energy/feasibility.py tests/test_energy.py
git commit -m "feat(python-api): energy 模块 — 逐段 SoC 可行性检查"
```

---

### Task 4: greedy_insert_stations — 策略 A(阈值触发 + 最近站 + 充满)

**Files:**
- Modify: `src/algorithms/task_allocation/energy/greedy.py`(替换占位)
- Test: `tests/test_energy.py`(追加)

**Interfaces:**
- Consumes: Task 1(`ChargeEvent` / `RechargePlan`)、Task 3 的矩阵语义
- Produces: `greedy_insert_stations(seq, e_matrix, stations, station_indices, B, sigma, speed, energy_per_meter) -> RechargePlan | None`
  - `stations`: `list[ChargingStation]`(用于取 `id` / `power`);`station_indices`: 对应的矩阵下标列表(长度一致)
  - 触发规则:到达下一节点后电量 `< σ` 时,选**绕行能耗最小**的站(并列时功率大者优先),充满;连站都够不到(`到站电量 < σ`)→ 返回 None
  - `plan.uav_id` 保持 `""`,由调用方回填

- [ ] **Step 1: 写失败测试** — `tests/test_energy.py` 追加:

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_energy.py -k greedy -v`
Expected: FAIL(NotImplementedError)

- [ ] **Step 3: 写实现** — 替换 `greedy.py` 占位:

```python
"""策略 A — 阈值触发 + 绕行最小站 + 充满"""

from __future__ import annotations

from .plan import ChargeEvent, RechargePlan


def greedy_insert_stations(
    seq: list[int],
    e_matrix,
    stations,
    station_indices: list[int],
    B: float,
    sigma: float | None,
    speed: float,
    energy_per_meter: float,
) -> RechargePlan | None:
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
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_energy.py -k greedy -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/algorithms/task_allocation/energy/greedy.py tests/test_energy.py
git commit -m "feat(python-api): energy 模块 — 贪心插站策略 A"
```

---

### Task 5: optimal_charging_dp — 策略 E(离散充电量 DP)

**Files:**
- Modify: `src/algorithms/task_allocation/energy/dp.py`(替换占位)
- Test: `tests/test_energy.py`(追加)

**Interfaces:**
- Consumes: Task 1、Task 3 的矩阵语义与数值基准
- Produces: `optimal_charging_dp(seq, e_matrix, stations, station_indices, B, sigma, speed, energy_per_meter, delta=None) -> RechargePlan | None`
  - 状态 = (序列位置, 连续电量),充电量只取 `battery_levels(B, delta)` 档;逐层支配剪枝(电量不低且时间不差则保留)
  - 返回给定序列下时间最优且终点电量 ≥ σ 的计划;无可行 → None

- [ ] **Step 1: 写失败测试** — `tests/test_energy.py` 追加:

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_energy.py -k dp -v`
Expected: FAIL(NotImplementedError)

- [ ] **Step 3: 写实现** — 替换 `dp.py` 占位:

```python
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


def optimal_charging_dp(
    seq: list[int],
    e_matrix,
    stations,
    station_indices: list[int],
    B: float,
    sigma: float | None,
    speed: float,
    energy_per_meter: float,
    delta: float | None = None,
) -> RechargePlan | None:
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
    end_feasible = [(e, t, prev) for e, (t, prev) in end.items() if e >= sigma - 1e-9]
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
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_energy.py -k dp -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add src/algorithms/task_allocation/energy/dp.py tests/test_energy.py
git commit -m "feat(python-api): energy 模块 — 离散充电量 DP 最优策略 E"
```

---

### Task 6: CW 嵌入 — 能量快检、_energy_repair、3 元组返回

**Files:**
- Modify: `src/algorithms/task_allocation/clarke_wright/solver.py`
- Modify: `src/algorithms/task_allocation/clarke_wright/capacity.py`
- Modify: `tests/test_task_allocation.py`(机械修改 3 处解包 + 追加新用例)
- Test: `tests/test_task_allocation.py`

**Interfaces:**
- Consumes: Task 1-5 全部产出;`capacity.feasible` 现有签名
- Produces:
  - `ClarkeWrightSolver(uavs, tasks, uav_max_ranges=None, energy_per_meter=0.1, stations=None, sigma=None, energy_strategy="greedy")`;`energy_strategy` 非法或 `sigma <= 0` 抛 `ValueError`
  - `ClarkeWrightSolver.build_recharge_plans(routes) -> list[RechargePlan]`(energy 关闭时返回 `[]`;每条路线一条,uav_id 已回填)
  - `clarke_wright_allocate(..., stations=None, sigma=None, energy_strategy="greedy", **kwargs) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]`

- [ ] **Step 1: 写失败测试** — `tests/test_task_allocation.py` 追加:

```python
# ── CW 能量嵌入 ──

def _cw_station(x: float, y: float, sid: str = "S") -> ChargingStation:
    return ChargingStation(id=sid, position=Position(x=x, y=y, z=0), power=700.0)


def test_cw_with_stations_merges_and_charges():
    # 1 机 B=100, T1(400,0)、T2(1000,0): 直飞 T2 后电量 0 < σ;
    # 站 S(450,0) 使合并可行: T1→S→T2, 充 45, 总时间 ≈ 331.43s
    uav = UAV(id="uav-0", position=Position(x=0, y=0, z=0), speed=10.0,
              max_payload=5.0, battery=100.0)
    t0 = Task(id="task-0", position=Position(x=400, y=0, z=0), payload_weight=1.0)
    t1 = Task(id="task-1", position=Position(x=1000, y=0, z=0), payload_weight=1.0)
    allocations, unassigned, plans = clarke_wright_allocate(
        [uav], [t0, t1], stations=[_cw_station(450, 0)], sigma=10.0
    )
    assert unassigned == []
    assert len(allocations) == 2
    assert len(plans) == 1
    p = plans[0]
    assert p.uav_id == "uav-0" and p.feasible is True
    assert len(p.charges) == 1
    assert p.charges[0].station_id == "S"
    assert p.charges[0].charge_wh == pytest.approx(45.0)
    assert p.total_time == pytest.approx(331.4286, rel=1e-3)


def test_cw_energy_repair_hands_off_unreachable():
    # uav-0 电池 50 够不到 T(800,0), 站也够不到 → 移交给能量余量大的 uav-1
    uav0 = UAV(id="uav-0", position=Position(x=0, y=0, z=0), speed=10.0,
               max_payload=5.0, battery=50.0)
    uav1 = UAV(id="uav-1", position=Position(x=2000, y=0, z=0), speed=10.0,
               max_payload=5.0, battery=1000.0)
    t0 = Task(id="task-0", position=Position(x=800, y=0, z=0), payload_weight=1.0)
    # uav_max_ranges 显式放宽, 避免 capacity.rebalance 抢在能量修复前移走任务
    solver = ClarkeWrightSolver(
        [uav0, uav1], [t0], stations=[_cw_station(0, 1000)], sigma=10.0,
        uav_max_ranges=[5000.0, 100000.0],
    )
    routes = solver.solve()
    plans = solver.build_recharge_plans(routes)
    assert routes[0] == []            # 任务已移出 uav-0
    assert routes[1] == [[0]]         # 移交给 uav-1
    assert len(plans) == 1
    assert plans[0].uav_id == "uav-1" and plans[0].feasible is True


def test_cw_energy_infeasible_marked_in_plan():
    # 单机、站不可达 → 任务保留, plan.feasible=False
    uav = UAV(id="uav-0", position=Position(x=0, y=0, z=0), speed=10.0,
              max_payload=5.0, battery=50.0)
    t0 = Task(id="task-0", position=Position(x=800, y=0, z=0), payload_weight=1.0)
    allocations, unassigned, plans = clarke_wright_allocate(
        [uav], [t0], stations=[_cw_station(0, 1000)], sigma=10.0
    )
    assert unassigned == [] and len(allocations) == 1  # 任务保留
    assert len(plans) == 1
    assert plans[0].feasible is False


def test_cw_without_stations_returns_empty_plans():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1")]
    allocations, unassigned, plans = clarke_wright_allocate(uavs, tasks)
    assert len(allocations) == 2 and unassigned == []
    assert plans == []


def test_cw_invalid_energy_strategy_raises():
    uavs = [_de_uav(0, 0, "uav-0")]
    tasks = [_de_task(10, 0, "task-0")]
    with pytest.raises(ValueError):
        ClarkeWrightSolver(uavs, tasks, stations=[_cw_station(50, 0)], energy_strategy="bogus")
```

- [ ] **Step 2: 机械修改既有解包(共 3 处,否则新签名会破坏既有测试)** — `tests/test_task_allocation.py`:

  - `test_cw_order_preserved`(约 357 行):`allocations, unassigned = clarke_wright_allocate(uavs, tasks)` → `allocations, unassigned, _plans = clarke_wright_allocate(uavs, tasks)`
  - `test_cw_empty_inputs`(约 365、367 行):两处 `allocations, unassigned = clarke_wright_allocate(...)` → 加 `, _plans`

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_task_allocation.py -k cw -v`
Expected: FAIL(新用例 ImportError/AttributeError;`stations` 参数不存在)

- [ ] **Step 4: 实现 capacity.feasible 扩展** — `capacity.py` 顶部 import 增加:

```python
from src.algorithms.task_allocation.energy import greedy_insert_stations, optimal_charging_dp
```

`feasible` 函数签名改为(追加 keyword-only 参数):

```python
def feasible(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uavs: list[UAV],
    tasks: list[Task],
    uav_max_ranges: list[float],
    uav_idx: int,
    route_list: list[list[int]],
    *,
    e_matrix=None,
    stations=None,
    station_indices=None,
    sigma: float | None = None,
    energy_strategy: str = "greedy",
    energy_per_meter: float = 0.1,
) -> bool:
```

现有距离/载荷检查**原样保留**在函数体前部;在 `return True` 之前追加能量检查:

```python
    # —— 能量检查(仅 energy 层启用时;构造期快检: 直飞或插站可行即放行)——
    if e_matrix is not None:
        uav = uavs[uav_idx]
        for route in route_list:
            seq = [uav_idx] + [n_uav + tid for tid in route]
            if energy_strategy == "dp":
                plan = optimal_charging_dp(
                    seq, e_matrix, stations, station_indices,
                    uav.battery, sigma, uav.speed, energy_per_meter,
                )
            else:
                plan = greedy_insert_stations(
                    seq, e_matrix, stations, station_indices,
                    uav.battery, sigma, uav.speed, energy_per_meter,
                )
            if plan is None:
                return False
    return True
```

注意:`capacity.rebalance` 里对 `feasible` 的调用**不加**能量参数(默认 None → 跳过能量检查,保持原语义)。

- [ ] **Step 5: 实现 solver 扩展** — `solver.py`:

  - import 增加:

```python
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
    build_energy_matrix,
)
from src.algorithms.task_allocation.energy import (
    RechargePlan,
    greedy_insert_stations,
    optimal_charging_dp,
)
```

  - `__init__` 签名与主体:

```python
    def __init__(
        self,
        uavs: list[UAV],
        tasks: list[Task],
        uav_max_ranges: list[float] | None = None,
        energy_per_meter: float = 0.1,
        stations: list | None = None,
        sigma: float | None = None,
        energy_strategy: str = "greedy",
    ):
        if energy_strategy not in ("greedy", "dp", "none"):
            raise ValueError(
                f"energy_strategy 必须为 greedy|dp|none，当前: {energy_strategy}"
            )
        if sigma is not None and sigma <= 0:
            raise ValueError(f"sigma 必须 > 0，当前: {sigma}")
        self.uavs = uavs
        self.tasks = tasks
        self.N_uav = len(uavs)
        self.N_task = len(tasks)
        self.energy_per_meter = energy_per_meter
        self.stations = stations or []
        self.sigma = sigma
        self.energy_strategy = energy_strategy
        self._energy_enabled = bool(self.stations) and energy_strategy != "none"
        self.uav_max_ranges = derive_uav_ranges(uavs, uav_max_ranges, energy_per_meter)
        if self._energy_enabled:
            self.e_matrix = build_energy_matrix(uavs, tasks, self.stations, energy_per_meter)
            self.station_indices = [self.N_uav + self.N_task + k for k in range(len(self.stations))]
        else:
            self.e_matrix = None
            self.station_indices = None
        self._build_cost_matrix()
```

  - `_feasible` 透传能量参数:

```python
    def _feasible(self, uav_idx: int, route_list: list[list[int]]) -> bool:
        return capacity.feasible(
            self.cost_matrix,
            self.N_uav,
            self.N_task,
            self.uavs,
            self.tasks,
            self.uav_max_ranges,
            uav_idx,
            route_list,
            e_matrix=self.e_matrix,
            stations=self.stations,
            station_indices=self.station_indices,
            sigma=self.sigma,
            energy_strategy=self.energy_strategy,
            energy_per_meter=self.energy_per_meter,
        )
```

  - 类内新增三个方法(`solve` 之后):

```python
    # ———— 能量计划 ————
    def _plan_for(self, uav_idx: int, route: list[int]) -> RechargePlan | None:
        """给定路线生成补给计划;energy 关闭时不会调用"""
        seq = [uav_idx] + [self.N_uav + tid for tid in route]
        uav = self.uavs[uav_idx]
        if self.energy_strategy == "dp":
            plan = optimal_charging_dp(
                seq, self.e_matrix, self.stations, self.station_indices,
                uav.battery, self.sigma, uav.speed, self.energy_per_meter,
            )
        else:
            plan = greedy_insert_stations(
                seq, self.e_matrix, self.stations, self.station_indices,
                uav.battery, self.sigma, uav.speed, self.energy_per_meter,
            )
        if plan is not None:
            plan.uav_id = uav.id
        return plan

    def _infeasible_plan(self, uav_idx: int, route: list[int]) -> RechargePlan:
        """插站失败且无处移交:标记不可行的占位计划(飞行代价仍给出)"""
        seq = [uav_idx] + [self.N_uav + tid for tid in route]
        uav = self.uavs[uav_idx]
        arrival_times = [0.0]
        total_energy = 0.0
        t = 0.0
        for prev, nxt in zip(seq, seq[1:]):
            total_energy += float(self.e_matrix[prev, nxt])
            t += float(self.e_matrix[prev, nxt]) / self.energy_per_meter / uav.speed
            arrival_times.append(t)
        return RechargePlan(
            uav_id=uav.id, node_seq=seq, charges=[],
            total_time=t, total_energy=total_energy,
            arrival_times=arrival_times, feasible=False,
        )

    def _energy_slack(self, uav_idx: int, routes: dict[int, list[list[int]]]) -> float:
        """能量余量 (Wh) = 电池 − 该机全部路线飞行能耗(插站前的粗估)"""
        used = 0.0
        for route in routes[uav_idx]:
            seq = [uav_idx] + [self.N_uav + tid for tid in route]
            used += sum(float(self.e_matrix[p, q]) for p, q in zip(seq, seq[1:]))
        return self.uavs[uav_idx].battery - used

    def _energy_repair(self, routes: dict[int, list[list[int]]]) -> dict[int, list[RechargePlan]]:
        """构造后修复:插站失败的任务移交给能量余量最大的可行目标"""
        last_moved: dict[int, int] = {}
        for _ in range(self.N_task + 1):
            moved = False
            for uav_idx in range(self.N_uav):
                for route in list(routes[uav_idx]):
                    if self._plan_for(uav_idx, route) is not None:
                        continue
                    task = route[-1]
                    targets = sorted(
                        (t for t in range(self.N_uav)
                         if t != uav_idx and last_moved.get(task) != t),
                        key=lambda t: -self._energy_slack(t, routes),
                    )
                    for target in targets:
                        if self._plan_for(target, [task]) is not None:
                            routes[uav_idx].remove(route)
                            route.pop()
                            if route:
                                routes[uav_idx].append(route)
                            routes[target].append([task])
                            last_moved[task] = uav_idx
                            moved = True
                            break
                    if moved:
                        break
                if moved:
                    break
            if not moved:
                break
        plans: dict[int, list[RechargePlan]] = {i: [] for i in range(self.N_uav)}
        for uav_idx, route_list in routes.items():
            for route in route_list:
                plan = self._plan_for(uav_idx, route)
                plans[uav_idx].append(
                    plan if plan is not None else self._infeasible_plan(uav_idx, route)
                )
        return plans

    def build_recharge_plans(self, routes: dict[int, list[list[int]]]) -> list[RechargePlan]:
        """对外:energy 关闭返回 [];否则每路线一条计划(uav 顺序、路线顺序)"""
        if not self._energy_enabled:
            return []
        plans = self._energy_repair(routes)
        return [p for uav_idx in range(self.N_uav) for p in plans[uav_idx]]
```

  - `clarke_wright_allocate` 函数替换为:

```python
def clarke_wright_allocate(
    uavs: list[UAV],
    tasks: list[Task],
    uav_max_ranges: list[float] | None = None,
    energy_per_meter: float = 0.1,
    stations: list | None = None,
    sigma: float | None = None,
    energy_strategy: str = "greedy",
    **kwargs,
) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]:
    """Clarke-Wright 任务分配 — 与 hungarian/auction/de 同签名

    返回 (allocations, unassigned, plans)。allocations 按 UAV 下标、路线创建
    顺序拼接输出，保留 CW 的访问顺序；CW 覆盖全部任务，
    unassigned 恒为空。plans 为每路线一条补给计划(无 stations 时为空)。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks], []

    solver = ClarkeWrightSolver(
        uavs=uavs,
        tasks=tasks,
        uav_max_ranges=uav_max_ranges,
        energy_per_meter=energy_per_meter,
        stations=stations,
        sigma=sigma,
        energy_strategy=energy_strategy,
    )
    routes = solver.solve()

    allocations: list[TaskAllocation] = []
    for uav_idx in range(len(uavs)):
        uav = uavs[uav_idx]
        for route in routes[uav_idx]:
            seg_costs = solver.route_segment_costs(uav_idx, route)
            for k, tid in enumerate(route):
                allocations.append(
                    TaskAllocation(
                        uav_id=uav.id,
                        task_id=tasks[tid].id,
                        estimated_cost=seg_costs[k],
                    )
                )
    plans = solver.build_recharge_plans(routes)
    return allocations, [], plans
```

  - 文档字符串 `__init__` 的类 docstring 保持,但 `solve()` 不变。

- [ ] **Step 6: 运行确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k cw -v`
Expected: PASS(既有 + 新增共约 16 个)

- [ ] **Step 7: 提交**

```bash
git add src/algorithms/task_allocation/clarke_wright/solver.py src/algorithms/task_allocation/clarke_wright/capacity.py tests/test_task_allocation.py
git commit -m "feat(python-api): CW 求解器接入能量快检与构造后补给修复"
```

---

### Task 7: DE 嵌入 — DP 内层最优法、缓存、3 元组返回

**Files:**
- Modify: `src/algorithms/task_allocation/differential_evolution/config.py`
- Modify: `src/algorithms/task_allocation/differential_evolution/fitness.py`
- Modify: `src/algorithms/task_allocation/differential_evolution/solver.py`
- Modify: `tests/test_task_allocation.py`(机械修改 6 处解包 + 追加新用例)

**Interfaces:**
- Consumes: Task 1-5 全部产出;`fitness.evaluate_constrained` 现有签名(新参数全部 keyword-only + 默认值,既有调用不受影响)
- Produces:
  - `config.ENERGY_INFEASIBLE_VIOLATION = 1.0`(不可行路线固定违反量)
  - `DiscreteDESolver(..., stations=None, sigma=None, energy_strategy="dp")`;非法 strategy / `sigma <= 0` 抛 `ValueError`
  - `DiscreteDESolver.recharge_plans(allocation) -> list[RechargePlan]`(energy 关闭返回 `[]`)
  - `de_allocate(..., stations=None, sigma=None, energy_strategy="dp", **kwargs) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]`
  - `fitness.evaluate_constrained(..., plan_fn=None, energy_enabled=False, energy_per_meter=0.1)`

- [ ] **Step 1: 写失败测试** — `tests/test_task_allocation.py` 追加:

```python
# ── DE 能量嵌入 ──

def test_de_with_stations_returns_plans():
    uavs = [
        _de_uav(0, 0, "uav-0", battery=100.0),
        _de_uav(100, 0, "uav-1", battery=100.0),
    ]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1")]
    stations = [ChargingStation(id="S", position=Position(x=50, y=0, z=0), power=700.0)]
    allocations, unassigned, plans = de_allocate(
        uavs, tasks, stations=stations, sigma=10.0,
        pop_size=10, generations=5, seed=0,
    )
    assert unassigned == [] and len(allocations) == 2
    assert len(plans) == 2  # 每机一条
    for p in plans:
        assert p.uav_id in ("uav-0", "uav-1")
        assert p.feasible is True
        assert p.total_time > 0


def test_de_fitness_with_energy_uses_real_time():
    # 1 机 1 任务, 距离 10m → 能耗 1Wh; 直飞到达电量 99 ≥ σ=10 → DP 取直飞
    # (绕站 S 需充 5Wh, 耗时 5+25.71+4=34.71s > 直飞 10s)
    # fitness = α·Σt + β·max_t + γ·500·violations = 1×10 + 0.5×10 + 0 = 15.0
    uavs = [_de_uav(0, 0, "uav-0", battery=100.0)]
    tasks = [_de_task(10, 0, "task-0")]
    stations = [ChargingStation(id="S", position=Position(x=50, y=0, z=0), power=700.0)]
    solver = DiscreteDESolver(uavs, tasks, stations=stations, sigma=10.0, seed=0)
    f = solver.evaluate_constrained([0])
    assert f == pytest.approx(15.0)


def test_de_without_stations_returns_empty_plans():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1")]
    allocations, unassigned, plans = de_allocate(uavs, tasks, seed=0, pop_size=10, generations=5)
    assert len(allocations) == 2 and unassigned == []
    assert plans == []


def test_de_invalid_energy_strategy_raises():
    uavs = [_de_uav(0, 0, "uav-0")]
    tasks = [_de_task(10, 0, "task-0")]
    with pytest.raises(ValueError):
        DiscreteDESolver(
            uavs, tasks,
            stations=[ChargingStation(id="S", position=Position(x=5, y=0, z=0), power=700.0)],
            energy_strategy="bogus",
        )
```

- [ ] **Step 2: 机械修改既有解包(共 6 处)** — `tests/test_task_allocation.py`:

  - `test_de_basic`(约 218 行):`allocations, unassigned = de_allocate(...)` → 加 `, _plans`
  - `test_de_empty_inputs`(约 228、230 行):两处 `allocations, unassigned = de_allocate(...)` → 加 `, _plans`
  - `test_de_ignores_unknown_kwargs`(约 237 行):`allocations, _ = de_allocate(...)` → `allocations, _, _ = de_allocate(...)`
  - `test_de_cluster_reasonable`(约 249 行):`allocations, unassigned = de_allocate(...)` → 加 `, _plans`
  - `test_de_seed_reproducible`(约 261-262 行):`a1, _ = de_allocate(...)` → `a1, _, _ = de_allocate(...)`;`a2` 同理
  - `test_de_allocate_accepts_warm_start`(约 418 行):`allocations, unassigned = de_allocate(...)` → 加 `, _plans`

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_task_allocation.py -k de -v`
Expected: FAIL(新用例 AttributeError/TypeError;`stations` 参数不存在)

- [ ] **Step 4: 实现 config 常量** — `config.py` 常量区追加:

```python
ENERGY_INFEASIBLE_VIOLATION = 1.0   # energy 层不可行路线的固定违反量(乘 penalty_weight)
```

- [ ] **Step 5: 实现 fitness 扩展** — `fitness.py`:

  - import 区(在 `from .config import ...` 行)追加常量 `ENERGY_INFEASIBLE_VIOLATION`。
  - `evaluate_constrained` 签名追加 keyword-only 参数:

```python
def evaluate_constrained(
    cost_matrix, n_uav, n_task, uavs, tasks, uav_max_ranges, individual,
    alpha=1.0, beta=0.5, gamma=1.0, penalty_weight=500.0,
    *,
    plan_fn=None,            # Callable[[uav_idx, seq], RechargePlan | None] — 内部带缓存
    energy_enabled: bool = False,
    energy_per_meter: float = 0.1,
) -> float:
```

  - 主循环中,对每架 UAV 的 `seq`,在现有路径代价计算**之前**插入分支:

```python
    for uav_id, seq in uav_task_dict.items():
        if not seq:
            continue
        if energy_enabled and plan_fn is not None:
            plan = plan_fn(uav_id, seq)
            if plan is not None:
                # 用真实时间(含充电)替换路径代价项(秒)
                total_path_cost += plan.total_time
                max_flight_time = max(max_flight_time, plan.total_time)
                # deadline 用真实到达时刻(节点序列中任务节点 = n_uav + tid)
                for p, node in enumerate(plan.node_seq):
                    if node >= n_uav:
                        tid = node - n_uav
                        task = tasks[tid]
                        if task.time_limit is not None and plan.arrival_times[p] > task.time_limit:
                            violations += DEADLINE_VIOLATION_PENALTY
            else:
                # 插站也修不好: 退回飞行时间 + 能量违反惩罚
                path_cost = sum(costs_dict[uav_id])
                speed = uavs[uav_id].speed
                fallback = path_cost / speed if speed > 0 else 0.0
                total_path_cost += fallback
                max_flight_time = max(max_flight_time, fallback)
                violations += ENERGY_INFEASIBLE_VIOLATION
            continue
        # —— 现状分支(无 stations 时逐字保留原逻辑,含约束 1)——
        path_cost = sum(costs_dict[uav_id])
        total_path_cost += path_cost
        ...
```

  > 现状分支的实现:把 fitness.py 中现有的主循环体(原文 `total_path_cost += path_cost`、约束 1、
  > `max_flight_time` 更新)和文件末尾的约束 2 deadline 循环、约束 3 负载均衡、fitness 计算**逐字保留**,
  > 仅套在 `if energy_enabled and plan_fn is not None: ... continue` 之后的代码路径上(即原顺序位置)。
  > 能量分支把 `plan.total_time` 累加进 `total_path_cost`(秒,米与秒不会同时在一次求解中出现:
  > energy_enabled 是全局开关,所有 UAV 走同一分支),`max_flight_time` 由 `max_time` 更新。
  > 能量分支已内联 deadline 真实时刻检查,故末尾约束 2 循环必须加 `if not energy_enabled:` 包裹
  > (否则同一任务会按纯飞行时间再计一次 deadline 惩罚)。约束 3 负载均衡不受影响,照旧执行。

- [ ] **Step 6: 实现 solver 扩展** — `solver.py`:

  - import 增加:

```python
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
    build_energy_matrix,
)
from src.algorithms.task_allocation.energy import (
    RechargePlan,
    greedy_insert_stations,
    optimal_charging_dp,
)
```

  - `__init__` 签名追加 `stations: list | None = None, sigma: float | None = None, energy_strategy: str = "dp"`,并在 `self._build_cost_matrix()` 之前追加:

```python
        if energy_strategy not in ("greedy", "dp", "none"):
            raise ValueError(f"energy_strategy 必须为 greedy|dp|none，当前: {energy_strategy}")
        if sigma is not None and sigma <= 0:
            raise ValueError(f"sigma 必须 > 0，当前: {sigma}")
        self.stations = stations or []
        self.sigma = sigma
        self.energy_strategy = energy_strategy
        self._energy_enabled = bool(self.stations) and energy_strategy != "none"
        if self._energy_enabled:
            self.e_matrix = build_energy_matrix(uavs, tasks, self.stations, self.config.energy_per_meter)
            self.station_indices = [self.N_uav + self.N_task + k for k in range(len(self.stations))]
        else:
            self.e_matrix = None
            self.station_indices = None
        self._dp_cache: dict[tuple[int, tuple[int, ...]], RechargePlan | None] = {}
```

  - 新增方法(放在 `compute_path_costs` 之后):

```python
    # ———— 补给计划(内层 DP, 带缓存) ————
    def _plan_for_seq(self, uav_idx: int, seq: list[int]) -> RechargePlan | None:
        """每机序列 → 补给计划;(uav_idx, seq) 全局缓存,整个进化过程复用"""
        key = (uav_idx, tuple(seq))
        if key in self._dp_cache:
            return self._dp_cache[key]
        seq_matrix = [uav_idx] + [self.N_uav + tid for tid in seq]
        uav = self.uavs[uav_idx]
        if self.energy_strategy == "greedy":
            plan = greedy_insert_stations(
                seq_matrix, self.e_matrix, self.stations, self.station_indices,
                uav.battery, self.sigma, uav.speed, self.config.energy_per_meter,
            )
        else:
            plan = optimal_charging_dp(
                seq_matrix, self.e_matrix, self.stations, self.station_indices,
                uav.battery, self.sigma, uav.speed, self.config.energy_per_meter,
            )
        self._dp_cache[key] = plan
        return plan

    def _infeasible_plan(self, uav_idx: int, seq: list[int]) -> RechargePlan:
        seq_matrix = [uav_idx] + [self.N_uav + tid for tid in seq]
        uav = self.uavs[uav_idx]
        arrival_times = [0.0]
        total_energy = 0.0
        t = 0.0
        for prev, nxt in zip(seq_matrix, seq_matrix[1:]):
            total_energy += float(self.e_matrix[prev, nxt])
            t += float(self.e_matrix[prev, nxt]) / self.config.energy_per_meter / uav.speed
            arrival_times.append(t)
        return RechargePlan(
            uav_id=uav.id, node_seq=seq_matrix, charges=[],
            total_time=t, total_energy=total_energy,
            arrival_times=arrival_times, feasible=False,
        )

    def recharge_plans(self, allocation: dict[int, list[int]]) -> list[RechargePlan]:
        """最优分配的补给计划;energy 关闭返回 []"""
        if not self._energy_enabled:
            return []
        plans: list[RechargePlan] = []
        for uav_idx, seq in allocation.items():
            if not seq:
                continue
            plan = self._plan_for_seq(uav_idx, seq)
            if plan is not None:
                plan.uav_id = self.uavs[uav_idx].id
                plans.append(plan)
            else:
                plans.append(self._infeasible_plan(uav_idx, seq))
        return plans
```

  - `evaluate_constrained` 方法追加 keyword-only 参数并透传给 fitness:

```python
    def evaluate_constrained(
        self,
        individual: list[int],
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 1.0,
        penalty_weight: float = 500.0,
    ) -> float:
        return fitness.evaluate_constrained(
            self.cost_matrix,
            self.N_uav,
            self.N_task,
            self.uavs,
            self.tasks,
            self.uav_max_ranges,
            individual,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            penalty_weight=penalty_weight,
            plan_fn=self._plan_for_seq if self._energy_enabled else None,
            energy_enabled=self._energy_enabled,
            energy_per_meter=self.config.energy_per_meter,
        )
```

  - `de_allocate` 函数替换为:

```python
def de_allocate(
    uavs: list[UAV],
    tasks: list[Task],
    pop_size: int = 50,
    generations: int = 100,
    F_init: float = 0.9,
    CR_init: float = 0.5,
    elite_guide_prob: float = 0.3,
    heuristic_ratio: float = 0.2,
    uav_max_ranges: list[float] | None = None,
    energy_per_meter: float = 0.1,
    penalty_weight: float = 500.0,
    seed: int | None = None,
    warm_start: list[int] | None = None,
    stations: list | None = None,
    sigma: float | None = None,
    energy_strategy: str = "dp",
    **kwargs,
) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]:
    """差分进化任务分配 — 与 hungarian/auction 同签名

    返回 (allocations, unassigned, plans)。allocations 按每架 UAV 的执行顺序
    排列(按 uav_id 分组即得任务序列);DE 编码覆盖全部任务,
    unassigned 恒为空。plans 为每机一条补给计划(无 stations 时为空)。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks], []

    solver = DiscreteDESolver(
        uavs=uavs,
        tasks=tasks,
        pop_size=pop_size,
        generations=generations,
        F_init=F_init,
        CR_init=CR_init,
        elite_guide_prob=elite_guide_prob,
        heuristic_ratio=heuristic_ratio,
        uav_max_ranges=uav_max_ranges,
        energy_per_meter=energy_per_meter,
        penalty_weight=penalty_weight,
        seed=seed,
        warm_start=warm_start,
        stations=stations,
        sigma=sigma,
        energy_strategy=energy_strategy,
    )
    allocation, _stats = solver.solve()

    allocations: list[TaskAllocation] = []
    for uav_idx, seq in allocation.items():
        costs = solver.compute_path_costs({uav_idx: seq})[uav_idx]
        uav = uavs[uav_idx]
        for k, task_idx in enumerate(seq):
            allocations.append(
                TaskAllocation(
                    uav_id=uav.id,
                    task_id=tasks[task_idx].id,
                    estimated_cost=costs[k],
                )
            )
    plans = solver.recharge_plans(allocation)
    return allocations, [], plans
```

- [ ] **Step 7: 运行确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k de -v`
Expected: PASS(既有 + 新增全部)。若 `test_de_fitness_with_energy_uses_real_time` 数值不符,按 Step 1 注释重新手算并修正断言后重跑。

- [ ] **Step 8: 提交**

```bash
git add src/algorithms/task_allocation/differential_evolution/config.py src/algorithms/task_allocation/differential_evolution/fitness.py src/algorithms/task_allocation/differential_evolution/solver.py tests/test_task_allocation.py
git commit -m "feat(python-api): DE 求解器接入内层 DP 补给计划(带缓存)"
```

---

### Task 8: 服务层 / API / 注册表 — 全链路打通

**Files:**
- Modify: `src/services/task_allocation/service.py`
- Modify: `src/schemas/task_allocation.py`
- Modify: `src/api/v1/endpoints/task_allocation.py`
- Modify: `src/algorithms/task_allocation/__init__.py`(cw/de 的 params_schema)
- Test: `tests/test_task_allocation.py`(追加 API 级用例)

**Interfaces:**
- Consumes: Task 6/7 的 3 元组入口、Task 1 的 `ChargingStation` / `RechargePlan`
- Produces:
  - `service.allocate(...)` 保持 2 元组(签名不变)
  - `service.allocate_with_plans(uavs, tasks, algorithm="hungarian", params=None, stations=None, sigma=None, energy_strategy="auto") -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]`
  - `AllocateRequest.stations: list[ChargingStation]`、`sigma: float | None`、`energy_strategy: str = "auto"`
  - `AllocateResponse.recharge_plans: list[UAVRechargePlanOut]`
  - 端点捕获 `ValueError` → 400

- [ ] **Step 1: 写失败测试** — `tests/test_task_allocation.py` 末尾追加:

```python
# ── API 级:stations / recharge_plans / 400 ──

import asyncio

from httpx import ASGITransport, AsyncClient
from src.main import app


def _api_allocate(payload: dict):
    async def _call():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/v1/tasks/allocate", json=payload)
    return asyncio.run(_call())


def test_allocate_api_with_stations_returns_recharge_plans():
    payload = {
        "uavs": [
            {"id": "uav-1", "position": {"x": 0, "y": 0, "z": 0}, "speed": 10.0,
             "max_payload": 5.0, "battery": 100.0, "status": "idle"},
        ],
        "tasks": [
            {"id": "task-1", "position": {"x": 400, "y": 0, "z": 0},
             "priority": "high", "payload_weight": 1.0},
        ],
        "algorithm": "cw",
        "stations": [
            {"id": "S", "position": {"x": 200, "y": 0, "z": 0}, "power": 700.0},
        ],
        "sigma": 10.0,
    }
    r = _api_allocate(payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["algorithm_used"] == "cw"
    assert len(body["recharge_plans"]) >= 1
    p = body["recharge_plans"][0]
    assert p["uav_id"] == "uav-1" and p["feasible"] is True
    assert "charges" in p and "total_time" in p and "total_energy" in p


def test_allocate_api_without_stations_backward_compatible():
    payload = {
        "uavs": [
            {"id": "uav-1", "position": {"x": 0, "y": 0, "z": 0}, "speed": 10.0,
             "max_payload": 5.0, "battery": 100.0, "status": "idle"},
        ],
        "tasks": [
            {"id": "task-1", "position": {"x": 400, "y": 0, "z": 0},
             "priority": "high", "payload_weight": 1.0},
        ],
        "algorithm": "cw",
    }
    r = _api_allocate(payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recharge_plans"] == []


def test_allocate_api_invalid_param_returns_400():
    payload = {
        "uavs": [
            {"id": "uav-1", "position": {"x": 0, "y": 0, "z": 0}, "speed": 10.0,
             "max_payload": 5.0, "battery": 100.0, "status": "idle"},
        ],
        "tasks": [
            {"id": "task-1", "position": {"x": 400, "y": 0, "z": 0},
             "priority": "high", "payload_weight": 1.0},
        ],
        "algorithm": "cw",
        "params": {"uav_max_ranges": [60.0, 60.0]},  # 长度 ≠ UAV 数
    }
    r = _api_allocate(payload)
    assert r.status_code == 400, r.text
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_task_allocation.py -k api -v`
Expected: FAIL(`recharge_plans` 字段不存在 / 500 而非 400)

- [ ] **Step 3: 实现 schemas** — `src/schemas/task_allocation.py`:

  - 第 5 行 import 改为:`from src.domain.models import UAV, Task, TaskAllocation, ChargingStation`
  - 文件末尾追加:

```python
class ChargeEventOut(BaseModel):
    """一次充电事件"""
    station_id: str
    charge_wh: float = Field(ge=0, description="充电量 (Wh)")
    arrive_time: float = Field(ge=0, description="到站时刻 (s)")
    leave_time: float = Field(ge=0, description="离站时刻 (s)")


class UAVRechargePlanOut(BaseModel):
    """一条路线的补给计划"""
    uav_id: str
    feasible: bool
    total_time: float = Field(ge=0, description="飞行 + 充电总时间 (s)")
    total_energy: float = Field(ge=0, description="总飞行能耗 (Wh)")
    charges: list[ChargeEventOut] = Field(default_factory=list)
```

  - `AllocateRequest` 追加字段:

```python
    stations: list[ChargingStation] = Field(default_factory=list, description="充电站列表(仅 cw/de 使用)")
    sigma: float | None = Field(default=None, gt=0, description="安全余量 (Wh),缺省 0.1×电池")
    energy_strategy: str = Field(default="auto", description="充电策略 greedy|dp|none|auto")
```

  - `AllocateResponse` 追加字段:

```python
    recharge_plans: list[UAVRechargePlanOut] = Field(default_factory=list, description="补给计划(每条路线一条)")
```

- [ ] **Step 4: 实现 service** — `src/services/task_allocation/service.py` 整体替换:

```python
"""④ 任务分配 — 分配编排"""

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms import get_algorithm, list_algorithms, AlgorithmCategory
from src.algorithms.task_allocation.energy import RechargePlan


def _resolve_strategy(algorithm: str, strategy: str) -> str:
    """energy_strategy 解析: auto → 算法默认;非法值抛 ValueError"""
    if strategy == "auto":
        strategy = {"cw": "greedy", "de": "dp"}.get(algorithm, "none")
    if strategy not in ("greedy", "dp", "none"):
        raise ValueError(f"energy_strategy 必须为 greedy|dp|none|auto，当前: {strategy}")
    return strategy


def _run(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str,
    params: dict | None,
    stations: list | None,
    sigma: float | None,
    energy_strategy: str,
) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]:
    """执行任务分配,返回 (分配结果, 未分配任务 ID, 补给计划)

    stations / sigma / energy_strategy 透传给所有算法;
    hungarian/auction 通过 **kwargs 吸收忽略。
    """
    algo_fn = get_algorithm(AlgorithmCategory.TASK_ALLOCATION, algorithm)
    kwargs = dict(params or {})
    kwargs["stations"] = stations or []
    kwargs["sigma"] = sigma
    kwargs["energy_strategy"] = _resolve_strategy(algorithm, energy_strategy)
    result = algo_fn(uavs, tasks, **kwargs)
    if len(result) == 3:
        return result
    return result[0], result[1], []


def allocate(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str = "hungarian",
    params: dict | None = None,
) -> tuple[list[TaskAllocation], list[str]]:
    """执行任务分配,返回 (分配结果, 未分配任务 ID)。签名与行为保持向后兼容。"""
    allocations, unassigned, _ = _run(uavs, tasks, algorithm, params, None, None, "auto")
    return allocations, unassigned


def allocate_with_plans(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str = "hungarian",
    params: dict | None = None,
    stations: list | None = None,
    sigma: float | None = None,
    energy_strategy: str = "auto",
) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]:
    """执行任务分配,返回 (分配结果, 未分配任务 ID, 补给计划)。供 API 端点使用。"""
    return _run(uavs, tasks, algorithm, params, stations, sigma, energy_strategy)


def list_available_algorithms() -> list[dict]:
    """列出可用的任务分配算法"""
    return list_algorithms(AlgorithmCategory.TASK_ALLOCATION)
```

- [ ] **Step 5: 实现端点** — `src/api/v1/endpoints/task_allocation.py` 替换为:

```python
"""④ 任务分配 API"""

from fastapi import APIRouter, HTTPException

from src.domain.exceptions import AlgorithmNotFoundError
from src.schemas.task_allocation import (
    AllocateRequest,
    AllocateResponse,
    ChargeEventOut,
    UAVRechargePlanOut,
)
from src.algorithms.task_allocation.energy import RechargePlan
from src.services import task_allocation as service

router = APIRouter()


def _to_plan_out(plan: RechargePlan) -> UAVRechargePlanOut:
    """RechargePlan → 响应 schema"""
    return UAVRechargePlanOut(
        uav_id=plan.uav_id,
        feasible=plan.feasible,
        total_time=plan.total_time,
        total_energy=plan.total_energy,
        charges=[
            ChargeEventOut(
                station_id=c.station_id,
                charge_wh=c.charge_wh,
                arrive_time=c.arrive_time,
                leave_time=c.leave_time,
            )
            for c in plan.charges
        ],
    )


@router.post("/allocate", response_model=AllocateResponse)
async def allocate_tasks(req: AllocateRequest) -> AllocateResponse:
    """提交任务分配请求"""
    try:
        allocations, unassigned, plans = service.allocate_with_plans(
            uavs=req.uavs,
            tasks=req.tasks,
            algorithm=req.algorithm,
            params=req.params,
            stations=req.stations,
            sigma=req.sigma,
            energy_strategy=req.energy_strategy,
        )
    except AlgorithmNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # 非法算法参数(uav_max_ranges 长度、energy_strategy、sigma 等)→ 400
        raise HTTPException(status_code=400, detail=str(e))

    return AllocateResponse(
        allocations=allocations,
        unassigned_tasks=unassigned,
        algorithm_used=req.algorithm,
        recharge_plans=[_to_plan_out(p) for p in plans],
    )


@router.get("/algorithms")
async def list_algorithms() -> list[dict]:
    """列出可用的任务分配算法"""
    return service.list_available_algorithms()
```

- [ ] **Step 6: 实现注册表 params_schema** — `src/algorithms/task_allocation/__init__.py`:

  - `de` 的 `params_schema` 末尾(seed / warm_start 之后)追加:

```python
                "sigma": {"type": "number", "default": None, "description": "安全余量 (Wh)，缺省 0.1×电池"},
                "energy_strategy": {"type": "string", "default": "auto", "description": "充电策略 greedy|dp|none，auto=算法默认"},
```

  - `cw` 的 `params_schema` 追加同样两条。

- [ ] **Step 7: 运行确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k "api or via_service" -v`
Expected: PASS(3 个新 API 用例 + 2 个既有 via_service 用例)

- [ ] **Step 8: 提交**

```bash
git add src/services/task_allocation/service.py src/schemas/task_allocation.py src/api/v1/endpoints/task_allocation.py src/algorithms/task_allocation/__init__.py tests/test_task_allocation.py
git commit -m "feat(python-api): 分配 API 支持 stations/sigma/energy_strategy 并输出补给计划"
```

---

### Task 9: 全量回归 + 真实服务冒烟

**Files:**
- 无代码改动(如有修复,随修复提交)

- [ ] **Step 1: 全量测试**

Run: `uv run pytest tests/ -v`
Expected: 全部 PASS。若有用例失败:先确认是否既有用例(向后兼容红线),修复到全绿为止;修复提交信息 `fix(python-api): …`。

- [ ] **Step 2: 真实服务冒烟(与用户验证过的流程一致)**

```bash
uv run uvicorn src.main:app --host 127.0.0.1 --port 8000
```

(后台运行;就绪后执行:)

```bash
curl -s http://localhost:8000/api/v1/tasks/algorithms | python -c "import sys,json; print([a['name'] for a in json.load(sys.stdin)])"
curl -s -X POST http://localhost:8000/api/v1/tasks/allocate -H "Content-Type: application/json" -d '{
  "uavs": [{"id":"uav-1","position":{"x":0,"y":0,"z":0},"speed":10.0,"max_payload":5.0,"battery":100.0,"status":"idle"}],
  "tasks": [{"id":"task-1","position":{"x":400,"y":0,"z":0},"priority":"high","payload_weight":1.0}],
  "algorithm": "cw",
  "stations": [{"id":"S","position":{"x":200,"y":0,"z":0},"power":700.0}],
  "sigma": 10.0
}'
```

Expected:算法列表仍为 4 个且 cw/de 的 params_schema 含 `sigma`/`energy_strategy`;POST 返回 200,`recharge_plans` 含 1 条 `feasible=true` 的计划;不带 stations 的请求 `recharge_plans == []`。

- [ ] **Step 3: 收尾确认**

Run: `git status --short`
Expected:仅剩未跟踪的 `scripts/`(验证脚本,不提交);无其他残留改动。

---

## 附:任务依赖图

```
Task 1 (模型/数据类) ─┬─> Task 3 (feasibility) ─┐
Task 2 (矩阵) ────────┴─> Task 4 (greedy) ─────┼─> Task 6 (CW) ─┐
                           Task 5 (dp) ────────┘               ├─> Task 8 (API) ─> Task 9
                                                               │
                                       Task 6/7 产物 ──> Task 7 (DE) ─┘
```

## 附:与 spec 的关键对应

| spec 要求 | 计划落点 |
|---|---|
| §3.1 ChargingStation 模型 | Task 1 |
| §3.2 距离/能耗矩阵 | Task 2 |
| §3.3 energy 模块(plan/feasibility/greedy/dp + 统一约定) | Task 1/3/4/5 |
| §3.4 CW 构造期快检 + _energy_repair | Task 6 |
| §3.5 DE v2 内层最优法 + 缓存 + 有站禁用约束 1 | Task 7 |
| §3.6 schemas / service / 端点 ValueError→400 / params_schema | Task 8 |
| §4 测试计划(§4 演算基准/兼容/API 级) | Task 1-9 各测试步骤 |
