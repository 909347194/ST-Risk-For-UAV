# Clarke-Wright 节约算法 + DE 热启动 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Clarke-Wright 节约算法（开放路线、航程+载荷容量约束），注册为独立算法 `cw`，并提供 DE `warm_start` 热启动参数。

**Architecture:** 抽公共模块 `_common.py`（PRIORITY_WEIGHT / build_cost_matrix / derive_uav_ranges，DE 与 CW 共用）；`ClarkeWrightSolver` 类（savings 合并 + 容量检查 + to_individual）+ `clarke_wright_allocate` 薄适配；DE 新增 `warm_start` 参数注入种群第 1 个个体。

**Tech Stack:** Python 3.12、numpy、pytest、现有 registry 模式。

**Spec:** `docs/superpowers/specs/2026-09-07-clarke-wright-warm-start-design.md`

## Global Constraints

- 所有改动仅限 `apps/server/python-fastapi-backend/` 目录（分支范围约束）
- 代价函数 = `欧氏距离 × PRIORITY_WEIGHT`，权重 `{"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}`，与 DE 现有逻辑逐行一致（DE 现有测试 `test_de_cost_matrix` 必须继续通过）
- `clarke_wright_allocate(uavs, tasks, **params) -> tuple[list[TaskAllocation], list[str]]`：unassigned 恒空；空输入返回 `([], [t.id for t in tasks])`；输出按 UAV 下标、路线创建顺序拼接，保留 CW 访问顺序
- CW 路线形态：开放路线（无返程段）；合并条件：同 UAV + 合并后航程 ≤ max_range + 总载荷 ≤ max_payload
- `warm_start: list[int] | None = None`：非 None 时校验 `len == N_task` 且元素 ∈ [0, N_uav)，非法抛 ValueError；种群[0] = warm_start，其余个体 `heuristic_ratio` 比例为 warm_start 扰动（每基因位 10% 翻转）、剩余随机；无 warm_start 时现有初始化行为零变化
- 注册名 `cw`、类别 `TASK_ALLOCATION`、注册信息含 params_schema（uav_max_ranges / energy_per_meter）
- 校验错误信息与 DE 现有风格一致（中文、含当前值）
- Commit 规范：`feat(python-api): 中文描述`（与分支现有提交一致）
- 所有测试命令在 `apps/server/python-fastapi-backend/` 目录下运行，用 `uv run`
- **不要 `git add` uv.lock**（仓库策略）

---

### Task 1: 抽取公共模块 _common.py + DE 切换 import

**Files:**
- Create: `src/algorithms/task_allocation/_common.py`
- Modify: `src/algorithms/task_allocation/differential_evolution.py`（删 PRIORITY_WEIGHT 定义与代价矩阵/航程推导代码，改 import）
- Test: `tests/test_task_allocation.py`（追加 derive_uav_ranges 测试；现有 DE 测试不动）

**Interfaces:**
- Consumes: `src.domain.models.UAV/Task`、`src.utils.utils.distance`
- Produces:
  - `_common.PRIORITY_WEIGHT: dict[str, float]`
  - `_common.build_cost_matrix(uavs: list[UAV], tasks: list[Task]) -> np.ndarray`（(N_uav+N_task)×(N_uav+N_task)，对角 0，进入任务的边 × 优先级权重）
  - `_common.derive_uav_ranges(uavs, uav_max_ranges=None, energy_per_meter=0.1) -> list[float]`（显式参数校验长度/正值，非法抛 ValueError；否则 battery/energy_per_meter，energy_per_meter<=0 时为 inf）
  - 后续任务依赖这三个接口

- [ ] **Step 1: 追加失败测试**

`tests/test_task_allocation.py` 顶部 import 区追加：

```python
from src.algorithms.task_allocation._common import derive_uav_ranges
```

文件末尾追加：

```python
def test_common_derive_uav_ranges():
    uavs = [_de_uav(0, 0, "uav-0", battery=1000.0)]
    assert derive_uav_ranges(uavs) == pytest.approx([10000.0])
    assert derive_uav_ranges(uavs, uav_max_ranges=[5.0]) == pytest.approx([5.0])
    assert derive_uav_ranges(uavs, energy_per_meter=0.0) == [float("inf")]
    with pytest.raises(ValueError):
        derive_uav_ranges(uavs, uav_max_ranges=[1.0, 2.0])
    with pytest.raises(ValueError):
        derive_uav_ranges(uavs, uav_max_ranges=[0.0])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_common_derive_uav_ranges -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.algorithms.task_allocation._common'`

- [ ] **Step 3: 创建 _common.py**

```python
"""任务分配算法公共模块 — 常量与代价/航程工具（DE / CW 共用）"""

import numpy as np

from src.domain.models import UAV, Task
from src.utils.utils import distance

PRIORITY_WEIGHT = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}


def build_cost_matrix(uavs: list[UAV], tasks: list[Task]) -> np.ndarray:
    """(N_uav+N_task)×(N_uav+N_task) 代价矩阵 — 距离 × 任务优先级权重，对角 0

    索引约定: 行/列 0..N_uav-1 为 UAV，N_uav..N_uav+N_task-1 为任务。
    """
    points = [u.position for u in uavs] + [t.position for t in tasks]
    n = len(points)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d = distance(points[i], points[j])
            if j >= len(uavs):
                task = tasks[j - len(uavs)]
                d *= PRIORITY_WEIGHT.get(task.priority.value, 1.0)
            matrix[i, j] = d
    return matrix


def derive_uav_ranges(
    uavs: list[UAV],
    uav_max_ranges: list[float] | None = None,
    energy_per_meter: float = 0.1,
) -> list[float]:
    """推导每机最大航程：显式参数优先（校验长度与正值），缺省按电池/能耗率推算"""
    if uav_max_ranges is not None:
        if len(uav_max_ranges) != len(uavs):
            raise ValueError(
                f"uav_max_ranges 长度必须等于 UAV 数 ({len(uavs)})，当前: {len(uav_max_ranges)}"
            )
        if any(r <= 0 for r in uav_max_ranges):
            raise ValueError(f"uav_max_ranges 各项必须 > 0，当前: {uav_max_ranges}")
        return list(uav_max_ranges)
    return [
        u.battery / energy_per_meter if energy_per_meter > 0 else float("inf")
        for u in uavs
    ]
```

- [ ] **Step 4: 修改 differential_evolution.py 使用公共模块**

(a) 顶部 import 区改为（删除 `import numpy as np` 之外的旧 `PRIORITY_WEIGHT` 定义，保留 numpy 等其他 import）：

```python
"""离散差分进化 (DE) 任务分配算法

参考：
  樊国政等《基于改进差分进化算法的同构无人机任务分配》
  Zhao et al., Acta Automatica Sinica, 2012, 38(12): 2038-2048.

核心思想：整数编码 + 连续空间差分变异 + 取整钳位修复
"""
import time

import numpy as np

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
)

```

> 注意：原文件的 `from src.utils.utils import distance` 一并删除（_build_cost_matrix 委托公共函数后 DE 内不再直接使用 distance）。

删除模块中原来的 `PRIORITY_WEIGHT = {...}` 定义行（原文件第 16 行附近）。

(b) `__init__` 中删除原来的 `uav_max_ranges` 校验块（`if uav_max_ranges is not None: ...` 部分），并把航程推导替换为公共函数：

原代码块（`self.rng = np.random.default_rng(seed)` 之后）：

```python
        # 最大航程: 显式参数优先, 否则按电池/能耗率推算
        if uav_max_ranges is not None:
            self.uav_max_ranges = list(uav_max_ranges)
        else:
            self.uav_max_ranges = [
                u.battery / energy_per_meter if energy_per_meter > 0 else float("inf")
                for u in uavs
            ]
```

以及其后的 `uav_max_ranges` 校验块（`if uav_max_ranges is not None:` 长度/正值校验）整体删除，替换为一行：

```python
        # 最大航程: 显式参数优先, 否则按电池/能耗率推算（校验在公共函数内）
        self.uav_max_ranges = derive_uav_ranges(uavs, uav_max_ranges, energy_per_meter)
```

> 注意：`__init__` 里 `pop_size` / `heuristic_ratio` 的校验块保持不动。

(c) `_build_cost_matrix` 方法体替换为：

```python
    # ———— 代价矩阵 ————
    def _build_cost_matrix(self) -> None:
        self.cost_matrix = build_cost_matrix(self.uavs, self.tasks)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -v`
Expected: 全部通过（现有 DE 测试含 test_de_cost_matrix 与 test_de_invalid_params_raise 不回归，新增 test_common_derive_uav_ranges 通过）

- [ ] **Step 6: Commit**

```bash
git add src/algorithms/task_allocation/_common.py src/algorithms/task_allocation/differential_evolution.py tests/test_task_allocation.py
git commit -m "feat(python-api): 抽取任务分配公共代价模块"
```

---

### Task 2: ClarkeWrightSolver 核心求解器

**Files:**
- Create: `src/algorithms/task_allocation/clarke_wright.py`
- Test: `tests/test_task_allocation.py`（追加 5 个测试）

**Interfaces:**
- Consumes: Task 1 的 `_common.build_cost_matrix` / `_common.derive_uav_ranges`
- Produces（后续任务依赖）:
  - `class ClarkeWrightSolver(uavs, tasks, uav_max_ranges=None, energy_per_meter=0.1)`
  - `solve() -> dict[int, list[list[int]]]`（每 UAV 的路线列表，每条路线为有序任务下标；路线按创建顺序排列）
  - `to_individual() -> list[int]`（内部调 solve；gene[tid] = 任务所属 UAV 下标）
  - `route_segment_costs(uav_idx, route) -> list[float]`（路线逐段代价，首段从该 UAV 位置出发）

- [ ] **Step 1: 追加失败测试**

`tests/test_task_allocation.py` 顶部 import 区追加：

```python
from src.algorithms.task_allocation.clarke_wright import ClarkeWrightSolver
```

文件末尾追加：

```python
# ── Clarke-Wright (CW) ──

def test_cw_basic():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = ClarkeWrightSolver(uavs, tasks)
    routes = solver.solve()
    assigned = sorted(t for route_list in routes.values() for route in route_list for t in route)
    assert assigned == [0, 1, 2]  # 全部分配且无重复


def test_cw_savings_merge():
    uavs = [_de_uav(0, 0, "uav-0")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(20, 0, "task-1")]
    # 共线同向: 节约值 10+20-10=20 > 0，合并为 [0, 1]
    solver = ClarkeWrightSolver(uavs, tasks)
    routes = solver.solve()
    assert routes[0] == [[0, 1]]


def test_cw_payload_capacity():
    uav = UAV(id="uav-0", position=Position(x=0, y=0, z=0), speed=10.0, max_payload=5.0, battery=1000.0)
    t0 = Task(id="task-0", position=Position(x=10, y=0, z=0), payload_weight=3.0)
    t1 = Task(id="task-1", position=Position(x=20, y=0, z=0), payload_weight=3.0)
    solver = ClarkeWrightSolver([uav], [t0, t1])
    routes = solver.solve()
    assert len(routes[0]) == 2  # 载荷 3+3 > 5 阻止合并，保持两条独立路线


def test_cw_range_capacity():
    uav = UAV(id="uav-0", position=Position(x=0, y=0, z=0), speed=10.0, max_payload=5.0, battery=1000.0)
    t0 = Task(id="task-0", position=Position(x=100, y=0, z=0), payload_weight=1.0)
    t1 = Task(id="task-1", position=Position(x=200, y=0, z=0), payload_weight=1.0)
    solver = ClarkeWrightSolver([uav], [t0, t1], uav_max_ranges=[150.0])
    routes = solver.solve()
    assert len(routes[0]) == 2  # 合并后航程 200 > 150 阻止合并


def test_cw_to_individual():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = ClarkeWrightSolver(uavs, tasks)
    ind = solver.to_individual()
    assert len(ind) == 3
    assert ind[0] == 0  # task-0 距 uav-0 最近
    assert ind[1] == 1  # task-1 距 uav-1 最近
    assert ind[2] == 0  # task-2 与两机等距，取 argmin 第一个
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_cw_basic -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.algorithms.task_allocation.clarke_wright'`

- [ ] **Step 3: 创建 clarke_wright.py**

```python
"""Clarke-Wright 节约算法 — 多机多任务构造启发式

参考：Clarke G, Wright J W. Scheduling of Vehicles from a Central Depot
to a Number of Delivery Points. Operations Research, 1964.
（开放路线变体：无返程段，与 DE 适应度模型一致）

角色：为 DE 提供高质量初始解（warm_start），也可独立使用。
"""

import numpy as np

from src.domain.models import UAV, Task
from src.algorithms.task_allocation._common import (
    build_cost_matrix,
    derive_uav_ranges,
)


class ClarkeWrightSolver:
    """Clarke-Wright 节约算法求解器

    开放路线多机场景：初始每个任务一条单点路线挂到最近 UAV，
    迭代贪心选取最大正节约值的同 UAV 路线对合并，容量约束为
    航程（≤ max_range）与载荷（总载荷 ≤ max_payload）。
    单点路线不校验自身可行性（任务本身必须被分配）。
    """

    def __init__(
        self,
        uavs: list[UAV],
        tasks: list[Task],
        uav_max_ranges: list[float] | None = None,
        energy_per_meter: float = 0.1,
    ):
        self.uavs = uavs
        self.tasks = tasks
        self.N_uav = len(uavs)
        self.N_task = len(tasks)
        self.uav_max_ranges = derive_uav_ranges(uavs, uav_max_ranges, energy_per_meter)
        self._build_cost_matrix()

    # ———— 代价矩阵 ————
    def _build_cost_matrix(self) -> None:
        self.cost_matrix = build_cost_matrix(self.uavs, self.tasks)

    # ———— 路线代价 ————
    def route_segment_costs(self, uav_idx: int, route: list[int]) -> list[float]:
        """路线逐段代价，首段从该 UAV 位置出发"""
        current = uav_idx
        seg: list[float] = []
        for tid in route:
            seg.append(float(self.cost_matrix[current, self.N_uav + tid]))
            current = self.N_uav + tid
        return seg

    # ———— 容量检查 ————
    def _feasible(self, uav_idx: int, route: list[int]) -> bool:
        """合并后航程与载荷约束检查"""
        if sum(self.route_segment_costs(uav_idx, route)) > self.uav_max_ranges[uav_idx]:
            return False
        payload = sum(self.tasks[tid].payload_weight for tid in route)
        if payload > self.uavs[uav_idx].max_payload:
            return False
        return True

    # ———— 求解 ————
    def solve(self) -> dict[int, list[list[int]]]:
        """返回 {uav_idx: [路线...]}，每条路线为有序任务下标列表"""
        routes: dict[int, list[list[int]]] = {i: [] for i in range(self.N_uav)}
        if not self.uavs or not self.tasks:
            return routes

        # 初始: 每个任务一条单点路线，挂到最近 UAV
        for tid in range(self.N_task):
            best_uav = int(np.argmin(self.cost_matrix[: self.N_uav, self.N_uav + tid]))
            routes[best_uav].append([tid])

        # 迭代贪心: 每次取最大正节约值的可行合并
        while True:
            best: tuple[float, int, int, int] | None = None  # (savings, uav_idx, a, b)
            for uav_idx, route_list in routes.items():
                depot = uav_idx
                for a in range(len(route_list)):
                    for b in range(len(route_list)):
                        if a == b:
                            continue
                        i = route_list[a][-1]  # 路线 a 的尾
                        j = route_list[b][0]   # 路线 b 的头
                        s = (
                            self.cost_matrix[depot, self.N_uav + i]
                            + self.cost_matrix[depot, self.N_uav + j]
                            - self.cost_matrix[self.N_uav + i, self.N_uav + j]
                        )
                        if s <= 0:
                            continue
                        merged = route_list[a] + route_list[b]
                        if not self._feasible(uav_idx, merged):
                            continue
                        if best is None or float(s) > best[0]:
                            best = (float(s), uav_idx, a, b)
            if best is None:
                break
            _, uav_idx, a, b = best
            route_list = routes[uav_idx]
            merged = route_list[a] + route_list[b]
            routes[uav_idx] = [r for idx, r in enumerate(route_list) if idx not in (a, b)]
            routes[uav_idx].append(merged)
        return routes

    # ———— 转为 DE 个体编码 ————
    def to_individual(self) -> list[int]:
        """路线 → DE 整数编码: gene[tid] = 该任务所属 UAV 下标"""
        routes = self.solve()
        individual = [0] * self.N_task
        for uav_idx, route_list in routes.items():
            for route in route_list:
                for tid in route:
                    individual[tid] = uav_idx
        return individual
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k "cw" -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/clarke_wright.py tests/test_task_allocation.py
git commit -m "feat(python-api): 添加 Clarke-Wright 节约算法求解器"
```

---

### Task 3: clarke_wright_allocate 适配 + 注册 + 服务层集成

**Files:**
- Modify: `src/algorithms/task_allocation/clarke_wright.py`（追加 `clarke_wright_allocate`）
- Modify: `src/algorithms/task_allocation/__init__.py`（注册 `cw`）
- Test: `tests/test_task_allocation.py`（追加 4 个测试）

**Interfaces:**
- Consumes: Task 2 的 `ClarkeWrightSolver.solve()` / `route_segment_costs()`；`src.algorithms.registry.register`
- Produces: `clarke_wright_allocate(uavs, tasks, **params) -> tuple[list[TaskAllocation], list[str]]`（注册名 `cw`，服务层 `allocate(algorithm="cw")` 直接可用）

- [ ] **Step 1: 追加失败测试**

`tests/test_task_allocation.py` 顶部 import 区把上一行改为：

```python
from src.algorithms.task_allocation.clarke_wright import ClarkeWrightSolver, clarke_wright_allocate
```

文件末尾追加：

```python
def test_cw_order_preserved():
    uavs = [_de_uav(0, 0, "uav-0")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(20, 0, "task-1")]
    allocations, unassigned = clarke_wright_allocate(uavs, tasks)
    assert [a.task_id for a in allocations] == ["task-0", "task-1"]  # CW 访问顺序保留
    assert unassigned == []


def test_cw_empty_inputs():
    uavs = [_de_uav(0, 0, "uav-0")]
    task = _de_task(10, 0, "task-0")
    allocations, unassigned = clarke_wright_allocate([], [task])
    assert allocations == [] and unassigned == ["task-0"]
    allocations, unassigned = clarke_wright_allocate(uavs, [])
    assert allocations == [] and unassigned == []


def test_cw_via_service():
    uavs = _make_uavs(2)
    tasks = _make_tasks(3)
    allocations, unassigned = allocate(uavs, tasks, algorithm="cw")
    assert len(allocations) == 3
    assert unassigned == []


def test_cw_listed_in_algorithms():
    from src.services import task_allocation as service
    names = [a["name"] for a in service.list_available_algorithms()]
    assert "cw" in names
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_cw_order_preserved -v`
Expected: FAIL — `ImportError: cannot import name 'clarke_wright_allocate'`

- [ ] **Step 3a: 追加 clarke_wright_allocate（clarke_wright.py 末尾）**

先把 clarke_wright.py 顶部 import 区的 `from src.domain.models import UAV, Task` 改为：

```python
from src.domain.models import UAV, Task, TaskAllocation
```

然后在文件末尾追加：

```python
def clarke_wright_allocate(
    uavs: list[UAV],
    tasks: list[Task],
    uav_max_ranges: list[float] | None = None,
    energy_per_meter: float = 0.1,
    **kwargs,
) -> tuple[list[TaskAllocation], list[str]]:
    """Clarke-Wright 任务分配 — 与 hungarian/auction/de 同签名

    返回 (allocations, unassigned)。allocations 按 UAV 下标、路线创建
    顺序拼接输出，保留 CW 的访问顺序；CW 覆盖全部任务，
    unassigned 恒为空。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks]

    solver = ClarkeWrightSolver(
        uavs=uavs,
        tasks=tasks,
        uav_max_ranges=uav_max_ranges,
        energy_per_meter=energy_per_meter,
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
    return allocations, []
```

- [ ] **Step 3b: 注册 cw（修改 task_allocation/__init__.py）**

顶部 import 区追加：

```python
from src.algorithms.task_allocation.clarke_wright import clarke_wright_allocate
```

`_register()` 内（`de` 注册之后）追加：

```python
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "cw",
        clarke_wright_allocate,
        {
            "name": "cw",
            "description": "Clarke-Wright 节约算法 — 构造启发式，多机多任务初始解 / DE 热启动",
            "params_schema": {
                "uav_max_ranges": {"type": "array", "default": None, "description": "每机最大航程 (m)，缺省按电池推算"},
                "energy_per_meter": {"type": "number", "default": 0.1, "description": "能耗率 (Wh/m)"},
            },
        },
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -v`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/clarke_wright.py src/algorithms/task_allocation/__init__.py tests/test_task_allocation.py
git commit -m "feat(python-api): 注册 CW 算法到任务分配模块"
```

---

### Task 4: DE warm_start 热启动参数

**Files:**
- Modify: `src/algorithms/task_allocation/differential_evolution.py`（__init__ / _init_population / de_allocate / 注册 schema）
- Modify: `src/algorithms/task_allocation/__init__.py`（de 的 params_schema 增加 warm_start）
- Test: `tests/test_task_allocation.py`（追加 4 个测试）

**Interfaces:**
- Consumes: Task 1 的 DE 现状（构造参数、_init_population、evaluate_constrained）
- Produces:
  - `DiscreteDESolver.__init__(..., warm_start: list[int] | None = None)`
  - `_init_population()`：有 warm_start 时种群[0]=warm_start、其余 heuristic_ratio 比例扰动（10% 翻转）+ 剩余随机
  - `de_allocate(..., warm_start: list[int] | None = None)` 透传

- [ ] **Step 1: 追加失败测试**

`tests/test_task_allocation.py` 末尾追加：

```python
def test_de_warm_start_seeds_population():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    ws = [0, 1, 1]
    solver = DiscreteDESolver(uavs, tasks, warm_start=ws, seed=0)
    pop = solver._init_population()
    assert pop[0].tolist() == ws
    assert pop.shape == (solver.pop_size, 3)


def test_de_warm_start_best_not_worse():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    ws = [0, 1, 1]
    solver = DiscreteDESolver(uavs, tasks, warm_start=ws, pop_size=20, generations=30, seed=0)
    _, stats = solver.solve()
    ws_fitness = solver.evaluate_constrained(ws)
    assert stats["best_cost"] <= ws_fitness + 1e-9  # 精英保留: 历史最优 ≤ 初始个体适应度


def test_de_warm_start_invalid():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    with pytest.raises(ValueError):
        DiscreteDESolver(uavs, tasks, warm_start=[0, 1])  # 长度错
    with pytest.raises(ValueError):
        DiscreteDESolver(uavs, tasks, warm_start=[0, 5, 1])  # 值域错


def test_de_allocate_accepts_warm_start():
    uavs = _make_uavs(2)
    tasks = _make_tasks(3)
    ws = [0, 1, 0]
    allocations, unassigned = de_allocate(
        uavs, tasks, warm_start=ws, pop_size=10, generations=10, seed=0
    )
    assert len(allocations) == 3
    assert unassigned == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_de_warm_start_seeds_population -v`
Expected: FAIL — `TypeError: DiscreteDESolver.__init__() got an unexpected keyword argument 'warm_start'`

- [ ] **Step 3: 实现 warm_start**

(a) `DiscreteDESolver.__init__` 签名在 `seed: int | None = None,` 之后追加参数：

```python
        warm_start: list[int] | None = None,
```

在现有校验块（pop_size / heuristic_ratio 校验）之后、`self.rng = np.random.default_rng(seed)` 之前插入：

```python
        # warm_start 校验: 长度与值域
        if warm_start is not None:
            if len(warm_start) != self.N_task:
                raise ValueError(
                    f"warm_start 长度必须等于任务数 ({self.N_task})，当前: {len(warm_start)}"
                )
            if any(not 0 <= g < self.N_uav for g in warm_start):
                raise ValueError(f"warm_start 基因值必须在 [0, {self.N_uav}) 区间")
        self.warm_start = warm_start
```

(b) `_init_population` 开头插入分支：

```python
    def _init_population(self) -> np.ndarray:
        if self.warm_start is not None:
            return self._init_population_with_warm_start()

        n_heuristic = max(1, int(self.pop_size * self.heuristic_ratio))
```

并把原方法体其余部分原样保留（`n_heuristic` 之后的代码不变）。

(c) 在 `_init_population` 之后新增方法：

```python
    # ———— 热启动初始化 ————
    def _init_population_with_warm_start(self) -> np.ndarray:
        """种群[0] = warm_start；其余 heuristic_ratio 比例为扰动个体，剩余随机"""
        pop: list[np.ndarray] = [np.array(self.warm_start, dtype=int)]
        n_perturbed = max(0, int((self.pop_size - 1) * self.heuristic_ratio))
        n_random = self.pop_size - 1 - n_perturbed
        base = np.array(self.warm_start, dtype=int)
        for _ in range(n_perturbed):
            ind = base.copy()
            flip_mask = self.rng.random(self.N_task) < 0.1
            ind[flip_mask] = self.rng.integers(0, self.N_uav, size=int(flip_mask.sum()))
            pop.append(ind)
        for _ in range(n_random):
            pop.append(self.rng.integers(0, self.N_uav, size=self.N_task))
        return np.array(pop)
```

(d) `de_allocate` 签名在 `seed: int | None = None,` 之后追加参数：

```python
    warm_start: list[int] | None = None,
```

并在 `DiscreteDESolver(...)` 构造调用里追加：

```python
        seed=seed,
        warm_start=warm_start,
    )
```

(e) `task_allocation/__init__.py` 中 `de` 的 params_schema 在 `"seed"` 条目后追加：

```python
                "warm_start": {"type": "array", "default": None, "description": "DE 热启动个体（整数编码，长度 = 任务数）"},
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k "warm_start or de_" -v`
Expected: 全部通过（含现有 DE 测试回归）

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/differential_evolution.py src/algorithms/task_allocation/__init__.py tests/test_task_allocation.py
git commit -m "feat(python-api): 添加 DE 热启动参数"
```

---

### Task 5: README 更新 + 全量回归

**Files:**
- Modify: `README.md`（内置算法表增加 `cw` 行）

**Interfaces:**
- Consumes: Task 3 的注册结果
- Produces: 文档与算法表一致

- [ ] **Step 1: 更新内置算法表**

`README.md` 中 `| 任务分配 | \`de\` | 离散差分进化 | 多机多任务，多约束场景 |` 行后追加：

```markdown
| 任务分配 | `cw` | Clarke-Wright 节约算法 | 构造启发式，多机多任务初始解 / DE 热启动 |
```

- [ ] **Step 2: 全量回归**

Run: `uv run pytest tests/ -v`
Expected: 全部通过（37 原有 + 14 新增 = 51 passed）

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(python-api): 内置算法表补充 CW 条目"
```

---

## 完成验收

- `uv run pytest tests/ -v` → 51 passed
- `POST /api/v1/tasks/allocate` body `{"algorithm": "cw", ...}` 返回 allocations + unassigned_tasks
- `GET /api/v1/tasks/algorithms` 列出 `cw` 与 `de`（de 含 warm_start 参数）
- CW 热启动路径可用：`clarke_wright_solver.to_individual()` → `de_allocate(..., warm_start=...)`
- 全部 commit 落在 `feat/python-api-backend` 分支，只改 `apps/server/python-fastapi-backend/` 目录
