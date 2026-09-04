# 差分进化（DE）任务分配算法 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `src/algorithms/task_allocation/` 移植离散差分进化求解器，作为第三个任务分配算法（`algorithm="de"`），服务层/端点零改动。

**Architecture:** 单文件 `differential_evolution.py`：`DiscreteDESolver` 类（参考代码 BaseSolver+ImprovedDESolver 合并，含代价矩阵、解码、自适应 F/CR、变异/交叉/修复、约束适应度、收敛检测）+ 薄适配函数 `de_allocate`（与 hungarian/auction 同签名），注册进 `task_allocation` 类别。

**Tech Stack:** Python 3.12、numpy（新增依赖）、pytest、现有 registry 模式。

**Spec:** `docs/superpowers/specs/2026-09-04-de-task-allocation-design.md`

## Global Constraints

- 所有改动仅限 `apps/server/python-fastapi-backend/` 目录（分支范围约束）
- 代价函数 = `欧氏距离 × PRIORITY_WEIGHT`，权重 `{"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}`，与 hungarian/auction 一致
- `de_allocate(uavs, tasks, **params) -> tuple[list[TaskAllocation], list[str]]`，签名与现有算法一致；`unassigned` 恒为 `[]`；空输入返回 `([], [t.id for t in tasks])`；未知 kwargs 忽略
- 注册名 `de`、类别 `TASK_ALLOCATION`、注册信息含 params_schema
- 3 类约束：最大航程（`uav_max_ranges` 或缺省 `battery/energy_per_meter`）、任务 deadline（`Task.time_limit`）、负载均衡（`np.var(任务数)×0.01`）
- numpy 版本下限 `>=1.26`
- Commit 规范：`feat(python-api): ...` / `chore(python-api): ...` / `docs(python-api): ...`（见 docs/CONTRIBUTING.md）
- 所有测试命令在 `apps/server/python-fastapi-backend/` 目录下运行，用 `uv run pytest`

---

### Task 1: 添加 numpy 依赖

**Files:**
- Modify: `pyproject.toml`（dependencies 增加 numpy）

**Interfaces:**
- Consumes: 无
- Produces: venv 内可 `import numpy`（后续任务硬依赖）

- [ ] **Step 1: 修改 pyproject.toml**

在 `[project] dependencies` 列表的 `"alembic>=1.14.0",` 之后加一行：

```toml
    "numpy>=1.26",
```

- [ ] **Step 2: 同步依赖并验证 numpy 可导入**

Run: `uv sync && uv run python -c "import numpy; print(numpy.__version__)"`
Expected: 打印 numpy 版本号（≥ 1.26），无报错

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(python-api): add numpy dependency"
```

---

### Task 2: DiscreteDESolver 骨架 + 代价矩阵 + 解码 + 路径代价

**Files:**
- Create: `src/algorithms/task_allocation/differential_evolution.py`
- Test: `tests/test_task_allocation.py`（追加测试与 import）

**Interfaces:**
- Consumes: `src.domain.models.UAV/Task/TaskAllocation`、`src.utils.utils.distance`
- Produces:
  - `class DiscreteDESolver`，构造参数：`uavs, tasks, pop_size=50, generations=100, F_init=0.9, CR_init=0.5, elite_guide_prob=0.3, heuristic_ratio=0.2, uav_max_ranges=None, energy_per_meter=0.1, alpha=1.0, beta=0.5, gamma=1.0, penalty_weight=500.0, seed=None`
  - 实例属性：`self.cost_matrix`（(N_uav+N_task)×(N_uav+N_task) ndarray）、`self.rng = np.random.default_rng(seed)`、`self.uav_max_ranges: list[float]`
  - 方法：`decode(individual) -> dict[int, list[int]]`、`compute_path_costs(uav_task_dict) -> dict[int, list[float]]`（后续任务依赖这两个方法）

- [ ] **Step 1: 追加测试（先写失败测试）**

`tests/test_task_allocation.py` 顶部 import 区改为：

```python
"""任务分配测试"""

import numpy as np
import pytest

from src.domain.models import UAV, Task, Position
from src.domain.enums import TaskPriority
from src.services.task_allocation import allocate
from src.algorithms.task_allocation.differential_evolution import DiscreteDESolver
```

文件末尾追加：

```python
# ── 差分进化 (DE) ──

def _de_uav(x: float, y: float, uid: str, battery: float = 1000.0, speed: float = 10.0) -> UAV:
    return UAV(id=uid, position=Position(x=x, y=y, z=0), speed=speed, max_payload=5.0, battery=battery)


def _de_task(x: float, y: float, tid: str, time_limit: float | None = None, priority: str = "low") -> Task:
    return Task(id=tid, position=Position(x=x, y=y, z=0), payload_weight=1.0, time_limit=time_limit, priority=TaskPriority(priority))


def test_de_cost_matrix():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(30, 0, "task-0", priority="low"), _de_task(60, 0, "task-1", priority="high")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    assert solver.cost_matrix[0, 2] == pytest.approx(30.0)    # uav0→task0: 30 × 1.0
    assert solver.cost_matrix[0, 3] == pytest.approx(120.0)   # uav0→task1: 60 × 2.0
    assert solver.cost_matrix[1, 2] == pytest.approx(70.0)    # uav1→task0: 70 × 1.0


def test_de_decode_nearest_neighbor():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(50, 0, "task-0"), _de_task(90, 0, "task-1")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    decoded = solver.decode([1, 1])  # 两个任务都给 uav1
    assert decoded[0] == []
    assert decoded[1] == [1, 0]  # 从 (100,0) 出发先到 90 再到 50


def test_de_compute_path_costs():
    uavs = [_de_uav(0, 0, "uav-0")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(30, 0, "task-1")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    costs = solver.compute_path_costs({0: [0, 1]})
    assert costs[0] == pytest.approx([10.0, 20.0])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_de_cost_matrix -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.algorithms.task_allocation.differential_evolution'`

- [ ] **Step 3: 创建 differential_evolution.py（骨架 + 代价矩阵 + 解码 + 路径代价）**

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
from src.utils.utils import distance

PRIORITY_WEIGHT = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}


class DiscreteDESolver:
    """离散差分进化求解器 — 多机多任务分配

    改进点（同参考实现）:
    1. 自适应 F/CR: F↓ (探索→开发), CR↑
    2. 约束感知适应度: 航程 / 任务 deadline / 负载均衡
    3. 精英引导变异: DE/current-to-best/1
    4. 启发式初始化: 贪心最近邻构造部分初始解
    5. seed 可复现（np.random.default_rng）
    """

    def __init__(
        self,
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
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 1.0,
        penalty_weight: float = 500.0,
        seed: int | None = None,
    ):
        self.uavs = uavs
        self.tasks = tasks
        self.N_uav = len(uavs)
        self.N_task = len(tasks)
        self.pop_size = pop_size
        self.gens = generations
        self.F_init = F_init
        self.CR_init = CR_init
        self.elite_guide_prob = elite_guide_prob
        self.heuristic_ratio = heuristic_ratio
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.penalty_weight = penalty_weight
        self.rng = np.random.default_rng(seed)

        # 最大航程: 显式参数优先, 否则按电池/能耗率推算
        if uav_max_ranges is not None:
            self.uav_max_ranges = list(uav_max_ranges)
        else:
            self.uav_max_ranges = [
                u.battery / energy_per_meter if energy_per_meter > 0 else float("inf")
                for u in uavs
            ]

        self._build_cost_matrix()

    # ———— 代价矩阵 ————
    def _build_cost_matrix(self) -> None:
        points = [u.position for u in self.uavs] + [t.position for t in self.tasks]
        n = len(points)
        self.cost_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                d = distance(points[i], points[j])
                if j >= self.N_uav:
                    task = self.tasks[j - self.N_uav]
                    d *= PRIORITY_WEIGHT.get(task.priority.value, 1.0)
                self.cost_matrix[i, j] = d

    # ———— 解码 ————
    def decode(self, individual: list[int] | np.ndarray) -> dict[int, list[int]]:
        """整数编码 → {uav_id: [task_id, ...]} (最近邻排序)

        个体: [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]
        """
        uav_tasks: dict[int, list[int]] = {i: [] for i in range(self.N_uav)}
        for task_id, uav_id in enumerate(individual):
            uav_tasks[int(uav_id)].append(task_id)

        sorted_tasks: dict[int, list[int]] = {}
        for uav_id, task_list in uav_tasks.items():
            if not task_list:
                sorted_tasks[uav_id] = []
                continue
            current_idx = uav_id  # 从 UAV 位置出发
            seq: list[int] = []
            remaining = task_list.copy()
            while remaining:
                nearest = min(
                    remaining,
                    key=lambda tid: self.cost_matrix[current_idx, self.N_uav + tid],
                )
                seq.append(nearest)
                remaining.remove(nearest)
                current_idx = self.N_uav + nearest
            sorted_tasks[uav_id] = seq
        return sorted_tasks

    # ———— 路径代价 ————
    def compute_path_costs(
        self, uav_task_dict: dict[int, list[int]]
    ) -> dict[int, list[float]]:
        """计算每架 UAV 任务序列的逐段代价"""
        costs: dict[int, list[float]] = {}
        for uav_id, seq in uav_task_dict.items():
            if not seq:
                costs[uav_id] = []
                continue
            current_idx = uav_id
            seg: list[float] = []
            for tid in seq:
                seg.append(float(self.cost_matrix[current_idx, self.N_uav + tid]))
                current_idx = self.N_uav + tid
            costs[uav_id] = seg
        return costs
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py::test_de_cost_matrix tests/test_task_allocation.py::test_de_decode_nearest_neighbor tests/test_task_allocation.py::test_de_compute_path_costs -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/differential_evolution.py tests/test_task_allocation.py
git commit -m "feat(python-api): add DE cost matrix and decoding"
```

---

### Task 3: 种群初始化 + 自适应参数 + 变异/交叉/修复

**Files:**
- Modify: `src/algorithms/task_allocation/differential_evolution.py`（类内新增 5 个方法）
- Test: `tests/test_task_allocation.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `DiscreteDESolver`（rng、cost_matrix、N_uav、N_task、pop_size、gens、F_init、CR_init、elite_guide_prob、heuristic_ratio）
- Produces:
  - `_init_population() -> np.ndarray`（shape (pop_size, N_task)，值 ∈ [0, N_uav)）
  - `_adaptive_params(gen) -> tuple[float, float]`
  - `_mutate(population, idx, best_idx, gen) -> np.ndarray`（float）
  - `_crossover(target, mutant, gen) -> np.ndarray`
  - `_repair(individual) -> np.ndarray`（int）

- [ ] **Step 1: 追加失败测试**

`tests/test_task_allocation.py` 末尾追加：

```python
def test_de_init_population():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = DiscreteDESolver(uavs, tasks, pop_size=20, seed=0)
    pop = solver._init_population()
    assert pop.shape == (20, 3)
    assert ((pop >= 0) & (pop < 2)).all()


def test_de_adaptive_params():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0")]
    solver = DiscreteDESolver(uavs, tasks, generations=10, seed=0)
    F0, CR0 = solver._adaptive_params(0)
    assert F0 == pytest.approx(0.9)
    assert CR0 == pytest.approx(0.5)
    F9, CR9 = solver._adaptive_params(9)
    assert F9 == pytest.approx(0.36)
    assert CR9 == pytest.approx(0.9)


def test_de_repair():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    ind = np.array([-0.4, 0.4, 1.6, 2.9])
    assert solver._repair(ind).tolist() == [0, 0, 1, 1]


def test_de_crossover_copies_at_least_one_gene():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    target = solver._init_population()[0]
    mutant = target.astype(float) + 100.0  # 任何被复制的位都必然不同于 target
    trial = solver._crossover(target, mutant, 0)
    assert not np.array_equal(trial, target)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_de_init_population -v`
Expected: FAIL — `AttributeError: 'DiscreteDESolver' object has no attribute '_init_population'`

- [ ] **Step 3: 在类内实现 5 个方法**

插入到 `compute_path_costs` 方法之后（`DiscreteDESolver` 类内）：

```python
    # ———— 自适应参数 ————
    def _adaptive_params(self, gen: int) -> tuple[float, float]:
        progress = gen / max(self.gens - 1, 1)
        F = self.F_init * (1.0 - 0.6 * progress)   # 0.9 → 0.36
        CR = self.CR_init + 0.4 * progress          # 0.5 → 0.9
        return F, CR

    # ———— 启发式初始化 ————
    def _init_population(self) -> np.ndarray:
        n_heuristic = max(1, int(self.pop_size * self.heuristic_ratio))
        n_random = self.pop_size - n_heuristic
        pop: list[np.ndarray] = []

        # 贪心构造 + 扰动
        for _ in range(n_heuristic):
            ind = np.zeros(self.N_task, dtype=int)
            for tid in range(self.N_task):
                best_uav = int(np.argmin(self.cost_matrix[: self.N_uav, self.N_uav + tid]))
                ind[tid] = best_uav
            # 10% 随机翻转
            flip_mask = self.rng.random(self.N_task) < 0.1
            ind[flip_mask] = self.rng.integers(0, self.N_uav, size=int(flip_mask.sum()))
            pop.append(ind)

        # 随机个体
        for _ in range(n_random):
            pop.append(self.rng.integers(0, self.N_uav, size=self.N_task))

        return np.array(pop)

    # ———— 精英引导变异 ————
    def _mutate(
        self,
        population: np.ndarray,
        idx: int,
        best_idx: int,
        gen: int,
    ) -> np.ndarray:
        F, _ = self._adaptive_params(gen)
        candidates = [i for i in range(self.pop_size) if i != idx]

        if self.rng.random() < self.elite_guide_prob and best_idx != idx:
            # DE/current-to-best/1
            r1, r2 = population[
                self.rng.choice(candidates, 2, replace=False)
            ]
            mutant = (
                population[idx].astype(float)
                + F * (population[best_idx].astype(float) - population[idx].astype(float))
                + F * (r1.astype(float) - r2.astype(float))
            )
        else:
            # DE/rand/1
            r1, r2, r3 = population[
                self.rng.choice(candidates, 3, replace=False)
            ]
            mutant = r1.astype(float) + F * (r2.astype(float) - r3.astype(float))

        return mutant

    # ———— 二项式交叉 ————
    def _crossover(
        self,
        target: np.ndarray,
        mutant: np.ndarray,
        gen: int,
    ) -> np.ndarray:
        _, CR = self._adaptive_params(gen)
        trial = target.astype(float)  # 人工裁决: 保留浮点管线，_repair 的 round 完成离散化（参考代码此处会 int 截断）
        j_rand = int(self.rng.integers(self.N_task))
        rand = self.rng.random(self.N_task)
        for j in range(self.N_task):
            if rand[j] < CR or j == j_rand:
                trial[j] = mutant[j]
        return trial

    # ———— 修复 ————
    def _repair(self, individual: np.ndarray) -> np.ndarray:
        """取整 → 钳位"""
        return np.clip(np.round(individual).astype(int), 0, self.N_uav - 1)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k "init_population or adaptive or repair or crossover" -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/differential_evolution.py tests/test_task_allocation.py
git commit -m "feat(python-api): add DE population init and operators"
```

---

### Task 4: 约束适应度评估

**Files:**
- Modify: `src/algorithms/task_allocation/differential_evolution.py`（新增 `evaluate`、`evaluate_constrained`）
- Test: `tests/test_task_allocation.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `decode` / `compute_path_costs` / `uav_max_ranges`、Task 3 无
- Produces:
  - `evaluate(individual) -> float`（基础适应度 = 总路径代价 + 超航程惩罚 10000.0）
  - `evaluate_constrained(individual, alpha=1.0, beta=0.5, gamma=1.0, penalty_weight=500.0) -> float`

- [ ] **Step 1: 追加失败测试**

```python
def test_de_evaluate_constrained_no_violation():
    uav = _de_uav(0, 0, "uav-0", battery=1000.0, speed=10.0)  # 默认航程 = 1000/0.1 = 10000
    task = _de_task(10, 0, "task-0")  # 无 time_limit
    solver = DiscreteDESolver([uav], [task], seed=0)
    fitness = solver.evaluate_constrained([0])
    # path_cost=10, flight_time=1.0, 违反量=0（单机 var=0）
    assert fitness == pytest.approx(10.0 + 0.5 * 1.0)  # 10.5


def test_de_evaluate_range_violation():
    uav = _de_uav(0, 0, "uav-0", battery=1000.0, speed=10.0)
    task = _de_task(10, 0, "task-0")
    solver = DiscreteDESolver([uav], [task], uav_max_ranges=[5.0], seed=0)
    fitness = solver.evaluate_constrained([0])
    # 违反量 = (10-5)/5 = 1.0
    assert fitness == pytest.approx(10.0 + 0.5 + 500.0 * 1.0)  # 510.5


def test_de_evaluate_deadline_violation():
    uav = _de_uav(0, 0, "uav-0", battery=1000.0, speed=10.0)
    task = _de_task(10, 0, "task-0", time_limit=0.5)
    solver = DiscreteDESolver([uav], [task], seed=0)
    fitness = solver.evaluate_constrained([0])
    # flight_time=1.0 > 0.5 → 违反量 0.5
    assert fitness == pytest.approx(10.0 + 0.5 + 500.0 * 0.5)  # 260.5


def test_de_evaluate_basic_prefers_shorter_path():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(5, 0, "task-0"), _de_task(105, 0, "task-1")]
    solver = DiscreteDESolver(uavs, tasks, seed=0)
    optimal = solver.evaluate([0, 1])   # 各自就近
    crossed = solver.evaluate([1, 0])   # 交叉远飞
    assert optimal < crossed
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_de_evaluate_constrained_no_violation -v`
Expected: FAIL — `AttributeError: 'DiscreteDESolver' object has no attribute 'evaluate_constrained'`

- [ ] **Step 3: 实现基础适应度与约束适应度**

插入到 `_repair` 方法之后（`DiscreteDESolver` 类内）：

```python
    # ———— 基础适应度 ————
    def evaluate(self, individual: list[int]) -> float:
        """基础适应度 = 总路径代价 + 超航程惩罚"""
        uav_task_dict = self.decode(individual)
        costs_dict = self.compute_path_costs(uav_task_dict)
        total_cost = 0.0
        for uav_id, seq in uav_task_dict.items():
            if not seq:
                continue
            seg_cost = sum(costs_dict[uav_id])
            if seg_cost > self.uav_max_ranges[uav_id]:
                total_cost += seg_cost + 10000.0  # 超航程惩罚
            else:
                total_cost += seg_cost
        return total_cost

    # ———— 约束感知适应度 (Zhao et al. 2012, Eq. 23) ————
    def evaluate_constrained(
        self,
        individual: list[int],
        alpha: float = 1.0,
        beta: float = 0.5,
        gamma: float = 1.0,
        penalty_weight: float = 500.0,
    ) -> float:
        """增强适应度 — 多约束惩罚

        fitness = alpha·Σ(path_cost) + beta·max_flight_time
                  + gamma·penalty_weight·Σ(constraint_violations)

        约束:
          1. 最大航程约束
          2. 任务 deadline 约束 (Task.time_limit)
          3. 负载均衡约束
        """
        uav_task_dict = self.decode(individual)
        costs_dict = self.compute_path_costs(uav_task_dict)
        total_path_cost = 0.0
        max_flight_time = 0.0
        violations = 0.0

        for uav_id, seq in uav_task_dict.items():
            if not seq:
                continue
            path_cost = sum(costs_dict[uav_id])
            total_path_cost += path_cost

            speed = self.uavs[uav_id].speed
            flight_time = path_cost / speed if speed > 0 else 0.0
            max_flight_time = max(max_flight_time, flight_time)

            # 约束 1: 最大航程
            max_range = self.uav_max_ranges[uav_id]
            if path_cost > max_range:
                violations += (path_cost - max_range) / max_range

        # 约束 2: 任务 deadline（累计到达时刻）
        for uav_id, seq in uav_task_dict.items():
            speed = self.uavs[uav_id].speed
            cumulative = 0.0
            for k, tid in enumerate(seq):
                if speed > 0:
                    cumulative += costs_dict[uav_id][k] / speed
                task = self.tasks[tid]
                if task.time_limit is not None and cumulative > task.time_limit:
                    violations += 0.5

        # 约束 3: 负载均衡
        task_counts = [len(seq) for seq in uav_task_dict.values()]
        if task_counts:
            violations += float(np.var(task_counts)) * 0.01

        fitness = (
            alpha * total_path_cost
            + beta * max_flight_time
            + gamma * penalty_weight * violations
        )
        return fitness
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k "evaluate" -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/differential_evolution.py tests/test_task_allocation.py
git commit -m "feat(python-api): add DE constrained fitness"
```

---

### Task 5: solve 主循环 + 收敛检测 + stats

**Files:**
- Modify: `src/algorithms/task_allocation/differential_evolution.py`（新增 `_fitness`、`_find_convergence`、`solve`）
- Test: `tests/test_task_allocation.py`（追加）

**Interfaces:**
- Consumes: Task 2/3/4 的全部方法
- Produces:
  - `solve() -> tuple[dict[int, list[int]], dict]`，stats 含 `algorithm/best_cost/convergence_gen/total_generations/time_seconds/history_min/history_avg`
  - `_find_convergence(history_min, tol=0.01) -> int`（staticmethod）

- [ ] **Step 1: 追加失败测试**

```python
def test_de_find_convergence():
    assert DiscreteDESolver._find_convergence([1.0, 1.0, 1.0, 1.0, 1.0, 1.0]) == 0
    assert DiscreteDESolver._find_convergence([0.0, 0.1, 0.2, 0.3, 0.4, 0.5]) == 5


def test_de_solve_covers_tasks_and_stats():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    solver = DiscreteDESolver(uavs, tasks, pop_size=20, generations=30, seed=0)
    allocation, stats = solver.solve()
    assigned = sorted(t for seq in allocation.values() for t in seq)
    assert assigned == [0, 1, 2]
    assert set(allocation.keys()) == {0, 1}
    assert stats["algorithm"] == "de"
    assert stats["convergence_gen"] <= stats["total_generations"]
    assert len(stats["history_min"]) == stats["total_generations"] + 1
    assert stats["time_seconds"] >= 0
    assert stats["best_cost"] > 0


def test_de_solve_seed_reproducible():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    s1 = DiscreteDESolver(uavs, tasks, seed=42)
    s2 = DiscreteDESolver(uavs, tasks, seed=42)
    a1, _ = s1.solve()
    a2, _ = s2.solve()
    assert a1 == a2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_de_solve_covers_tasks_and_stats -v`
Expected: FAIL — `AttributeError: 'DiscreteDESolver' object has no attribute 'solve'`

- [ ] **Step 3: 实现主循环**

插入到 `evaluate_constrained` 方法之后（`DiscreteDESolver` 类内）：

```python
    # ———— 适应度 ————
    def _fitness(self, individual: np.ndarray) -> float:
        return self.evaluate_constrained(
            list(individual),
            alpha=self.alpha,
            beta=self.beta,
            gamma=self.gamma,
            penalty_weight=self.penalty_weight,
        )

    # ———— 收敛检测 ————
    @staticmethod
    def _find_convergence(history_min: list[float], tol: float = 0.01) -> int:
        for i in range(len(history_min) - 5):
            if abs(history_min[i] - history_min[i + 5]) < tol:
                return i
        return len(history_min) - 1

    # ———— 主循环 ————
    def solve(self) -> tuple[dict[int, list[int]], dict]:
        t0 = time.perf_counter()

        population = self._init_population()
        fitness = np.array([self._fitness(ind) for ind in population])

        best_idx = int(np.argmin(fitness))
        best_ind = population[best_idx].copy()
        best_cost = float(fitness[best_idx])

        history_min = [best_cost]
        history_avg = [float(np.mean(fitness))]

        for gen in range(self.gens):
            for i in range(self.pop_size):
                mutant = self._mutate(population, i, best_idx, gen)
                trial_cont = self._crossover(population[i], mutant, gen)
                trial_int = self._repair(trial_cont)
                trial_fit = self._fitness(trial_int)

                if trial_fit <= fitness[i]:
                    population[i] = trial_int
                    fitness[i] = trial_fit
                    if trial_fit < best_cost:
                        best_ind = trial_int.copy()
                        best_cost = trial_fit

            history_min.append(best_cost)
            history_avg.append(float(np.mean(fitness)))

        elapsed = time.perf_counter() - t0
        best_allocation = self.decode(list(best_ind))
        convergence_gen = self._find_convergence(history_min)

        return best_allocation, {
            "algorithm": "de",
            "best_cost": best_cost,
            "convergence_gen": convergence_gen,
            "total_generations": self.gens,
            "time_seconds": round(elapsed, 4),
            "history_min": history_min,
            "history_avg": history_avg,
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -k "solve or convergence" -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/differential_evolution.py tests/test_task_allocation.py
git commit -m "feat(python-api): add DE solve loop with convergence stats"
```

---

### Task 6: de_allocate 适配函数 + 注册 + 服务层集成

**Files:**
- Modify: `src/algorithms/task_allocation/differential_evolution.py`（新增 `de_allocate`）
- Modify: `src/algorithms/task_allocation/__init__.py`（注册 `de`）
- Test: `tests/test_task_allocation.py`（追加）

**Interfaces:**
- Consumes: Task 5 的 `DiscreteDESolver.solve()`；`src.algorithms.registry.register`
- Produces: `de_allocate(uavs, tasks, **params) -> tuple[list[TaskAllocation], list[str]]`（注册名 `de`，服务层 `allocate(algorithm="de")` 直接可用）

- [ ] **Step 1: 追加失败测试**

`tests/test_task_allocation.py` 顶部 import 区把上一行改为：

```python
from src.algorithms.task_allocation.differential_evolution import DiscreteDESolver, de_allocate
```

文件末尾追加：

```python
def test_de_basic():
    uavs = _make_uavs(2)
    tasks = _make_tasks(3)
    allocations, unassigned = de_allocate(uavs, tasks, seed=42, pop_size=20, generations=30)
    assert unassigned == []
    pairs = {(a.uav_id, a.task_id) for a in allocations}
    assert len(pairs) == 3  # 全分配、无重复对
    assert all(a.estimated_cost >= 0 for a in allocations)


def test_de_empty_inputs():
    uavs = [_de_uav(0, 0, "uav-0")]
    task = _de_task(10, 0, "task-0")
    allocations, unassigned = de_allocate([], [task])
    assert allocations == [] and unassigned == ["task-0"]
    allocations, unassigned = de_allocate(uavs, [])
    assert allocations == [] and unassigned == []


def test_de_ignores_unknown_kwargs():
    uavs = _make_uavs(2)
    tasks = _make_tasks(2)
    allocations, _ = de_allocate(uavs, tasks, seed=0, unknown_thing=123)
    assert len(allocations) == 2


def test_de_cluster_reasonable():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [
        _de_task(5, 5, "task-0"),
        _de_task(-5, 5, "task-1"),
        _de_task(105, 5, "task-2"),
        _de_task(95, 5, "task-3"),
    ]
    allocations, unassigned = de_allocate(uavs, tasks, pop_size=40, generations=100, seed=0)
    assert unassigned == []
    by_task = {a.task_id: a.uav_id for a in allocations}
    assert by_task["task-0"] == "uav-0"
    assert by_task["task-1"] == "uav-0"
    assert by_task["task-2"] == "uav-1"
    assert by_task["task-3"] == "uav-1"


def test_de_seed_reproducible():
    uavs = [_de_uav(0, 0, "uav-0"), _de_uav(100, 0, "uav-1")]
    tasks = [_de_task(10, 0, "task-0"), _de_task(90, 0, "task-1"), _de_task(50, 0, "task-2")]
    a1, _ = de_allocate(uavs, tasks, seed=42)
    a2, _ = de_allocate(uavs, tasks, seed=42)
    key = lambda a: sorted((x.uav_id, x.task_id, x.estimated_cost) for x in a)
    assert key(a1) == key(a2)


def test_de_via_service():
    uavs = _make_uavs(2)
    tasks = _make_tasks(3)
    allocations, unassigned = allocate(uavs, tasks, algorithm="de", params={"seed": 0, "pop_size": 10, "generations": 10})
    assert len(allocations) == 3
    assert unassigned == []


def test_de_listed_in_algorithms():
    from src.services import task_allocation as service
    names = [a["name"] for a in service.list_available_algorithms()]
    assert "de" in names
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_task_allocation.py::test_de_basic -v`
Expected: FAIL — `ImportError: cannot import name 'de_allocate'`

- [ ] **Step 3a: 实现 de_allocate（追加到 differential_evolution.py 末尾）**

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
    **kwargs,
) -> tuple[list[TaskAllocation], list[str]]:
    """差分进化任务分配 — 与 hungarian/auction 同签名

    返回 (allocations, unassigned)。allocations 按每架 UAV 的执行顺序
    排列（按 uav_id 分组即得任务序列）；DE 编码覆盖全部任务，
    unassigned 恒为空。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks]

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
    return allocations, []
```

- [ ] **Step 3b: 注册 de（修改 task_allocation/__init__.py）**

`src/algorithms/task_allocation/__init__.py` 顶部 import 区改为：

```python
"""任务分配算法"""

from src.algorithms.registry import register, AlgorithmCategory
from src.algorithms.task_allocation.hungarian import hungarian_allocate
from src.algorithms.task_allocation.auction import auction_allocate
from src.algorithms.task_allocation.differential_evolution import de_allocate
```

`_register()` 内（`auction` 注册之后）追加：

```python
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "de",
        de_allocate,
        {
            "name": "de",
            "description": "离散差分进化 — 多机多任务分配，约束感知适应度，自适应 F/CR",
            "params_schema": {
                "pop_size": {"type": "integer", "default": 50, "description": "种群规模"},
                "generations": {"type": "integer", "default": 100, "description": "进化代数"},
                "F_init": {"type": "number", "default": 0.9, "description": "差分权重初值"},
                "CR_init": {"type": "number", "default": 0.5, "description": "交叉率初值"},
                "elite_guide_prob": {"type": "number", "default": 0.3, "description": "精英引导变异概率"},
                "heuristic_ratio": {"type": "number", "default": 0.2, "description": "启发式初始化占比"},
                "uav_max_ranges": {"type": "array", "default": None, "description": "每机最大航程 (m)，缺省按电池推算"},
                "energy_per_meter": {"type": "number", "default": 0.1, "description": "能耗率 (Wh/m)"},
                "seed": {"type": "integer", "default": None, "description": "随机种子"},
            },
        },
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_task_allocation.py -v`
Expected: 全部通过（原有 4 + 新增 21 = 25 passed）

- [ ] **Step 5: Commit**

```bash
git add src/algorithms/task_allocation/differential_evolution.py src/algorithms/task_allocation/__init__.py tests/test_task_allocation.py
git commit -m "feat(python-api): register DE in task allocation algorithms"
```

---

### Task 7: README 更新 + 全量回归

**Files:**
- Modify: `README.md`（内置算法表增加 `de` 行）

**Interfaces:**
- Consumes: Task 6 的注册结果
- Produces: 文档与算法表一致

- [ ] **Step 1: 更新内置算法表**

`README.md` 中 `| 任务分配 | \`auction\` | 拍卖算法 | 分布式竞价，大规模动态场景 |` 行后追加：

```markdown
| 任务分配 | `de` | 离散差分进化 | 多机多任务，多约束场景 |
```

- [ ] **Step 2: 全量回归**

Run: `uv run pytest tests/ -v`
Expected: 全部通过（14 原有 + 21 新增 = 35 passed）

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(python-api): list DE in built-in algorithms table"
```

---

## 完成验收

- `uv run pytest tests/ -v` → 35 passed
- `POST /api/v1/tasks/allocate` body `{"algorithm": "de", ...}` 返回 allocations + unassigned_tasks
- `GET /api/v1/tasks/algorithms` 列出 `de` 及其 params_schema
- 全部 commit 落在 `feat/python-api-backend` 分支，只改 `apps/server/python-fastapi-backend/` 目录
