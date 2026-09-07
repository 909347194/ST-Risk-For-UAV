# Clarke-Wright 节约算法 + DE 热启动 — 设计文档

日期：2026-09-07
分支：feat/python-api-backend
参考：[docs/architecture/algorithms/task-allocation/任务分配算法方案.md](../../../../../architecture/algorithms/task-allocation/任务分配算法方案.md)（第二层 Clarke-Wright）

## 1. 背景与目标

按四层互补架构的 Phase 2 要求，实现 Clarke-Wright（CW）节约算法作为构造启发式：
输出高质量的初始可行解，既可作为独立注册算法使用，也作为 DE 的 warm_start
（DE 种群第 1 个个体 + 扰动个体），加速 DE 收敛。

## 2. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 交付范围 | 热启动构造器 + 独立注册算法（`algorithm="cw"`） |
| 文件位置 | `src/algorithms/task_allocation/clarke_wright.py`（snake_case 惯例） |
| 路线形态 | 开放路线（UAV→任务序列，无返程段），与 DE 适应度模型一致；文档的返回起点/就近机巢策略暂不实现（domain 无机巢模型） |
| 容量约束 | 航程（≤ max_range）+ 载荷（总载荷 ≤ max_payload）；deadline/负载均衡交给 DE 罚分 |
| DE 集成 | `DiscreteDESolver` 与 `de_allocate` 新增 `warm_start: list[int] \| None = None` 参数 |
| 顺序处理 | 独立输出保留 CW 访问顺序；注入 DE 时转为纯分配编码，顺序由 decode 最近邻重排（不改 DE 编码） |
| 代码结构 | 类为核心 + 抽公共模块 `_common.py`（PRIORITY_WEIGHT / build_cost_matrix / derive_uav_ranges），DE 与 CW 共用 |

## 3. 文件与类结构

### 3.1 `_common.py`（新增）

```python
PRIORITY_WEIGHT = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}

def build_cost_matrix(uavs: list[UAV], tasks: list[Task]) -> np.ndarray
    # (N_uav+N_task)×(N_uav+N_task)，对角 0；进入任务的边 × PRIORITY_WEIGHT[task.priority.value]
    # 与 DiscreteDESolver._build_cost_matrix 现有逻辑逐行一致

def derive_uav_ranges(uavs, uav_max_ranges, energy_per_meter) -> list[float]
    # 显式参数优先（校验长度 == N_uav、各项 > 0，非法抛 ValueError，同 DE 现有校验）；
    # 否则 battery / energy_per_meter（energy_per_meter <= 0 时为 inf）
```

DE 改为 import 公共函数，逻辑零变化。hungarian.py / auction.py 的重复
PRIORITY_WEIGHT 本次不动（控制 diff 范围）。

### 3.2 `clarke_wright.py`（新增）

```python
class ClarkeWrightSolver:
    def __init__(self, uavs, tasks, uav_max_ranges=None, energy_per_meter=0.1)

    def solve(self) -> dict[int, list[list[int]]]:
        # 每 UAV 的路线列表，每条路线为有序任务下标（容量约束阻止的合并保持独立路线，不拼接）
        # 1. 初始: 每个任务一条单点路线，挂到距离最近的 UAV
        # 2. 节约值 s(i,j) = d(depot,i) + d(depot,j) - d(i,j)（开放路线版）
        #    对同 depot 的路线对降序排列
        # 3. 按节约值降序合并: 两路线同属一架 UAV，且合并后航程 ≤ max_range、
        #    总载荷 ≤ max_payload → 尾-头拼接；否则跳过
        # 4. 无可合并对时结束，返回路线列表（路线按创建顺序排列，即初始任务下标升序）

    def to_individual(self) -> list[int]:
        # 路线 → DE 整数编码: gene[tid] = 该任务所属 UAV 下标（与路线数/顺序无关）
```

薄适配函数：

```python
def clarke_wright_allocate(uavs, tasks, **params) -> tuple[list[TaskAllocation], list[str]]
    # 签名与 hungarian/auction/de 一致；输出时按 UAV 下标、路线创建顺序将多条路线
    # 拼接为一条序列，TaskAllocation 按该访问顺序输出（顺序保留）
    # unassigned 恒空（CW 覆盖全部任务）；空输入返回 ([], [t.id for t in tasks])
```

### 3.3 `differential_evolution.py`（修改）

- `DiscreteDESolver.__init__` 新增 `warm_start: list[int] | None = None`：
  非 None 时校验 `len == N_task` 且元素 ∈ [0, N_uav)，非法抛 ValueError（并入现有校验块）
- `_init_population()`：
  - 有 warm_start：种群[0] = warm_start；其余个体中 `heuristic_ratio` 比例为
    warm_start 扰动（每基因位 10% 随机翻转，与现有贪心扰动一致），剩余为随机个体
  - 无 warm_start：现有贪心+随机逻辑不变（行为零变化）
- `de_allocate` 透传 `warm_start` 参数；注册 params_schema 增加
  `"warm_start": {"type": "array", "default": None, "description": "DE 热启动个体（整数编码）"}`

### 3.4 `__init__.py`（修改）

`_register()` 增加：

```python
register(AlgorithmCategory.TASK_ALLOCATION, "cw", clarke_wright_allocate, {
    "name": "cw",
    "description": "Clarke-Wright 节约算法 — 构造启发式，多机多任务初始解 / DE 热启动",
    "params_schema": {
        "uav_max_ranges": {"type": "array", "default": None, "description": "每机最大航程 (m)，缺省按电池推算"},
        "energy_per_meter": {"type": "number", "default": 0.1, "description": "能耗率 (Wh/m)"},
    },
})
```

## 4. 数据流

```
POST /tasks/allocate {algorithm: "cw"}  →  clarke_wright_allocate → CW 路线（顺序保留）→ TaskAllocation 列表

CW 热启动路径:
  solver = ClarkeWrightSolver(uavs, tasks)
  individual = solver.to_individual()
  de_allocate(uavs, tasks, warm_start=individual, ...)
    → DiscreteDESolver(warm_start=...) → 种群[0]=CW 解，其余扰动/随机 → DE 进化
```

## 5. 测试计划（先写测试，后实现）

`tests/test_task_allocation.py` 增加：

1. `test_cw_basic`：2 机 3 任务，全分配、无重复对、代价非负
2. `test_cw_savings_merge`：两任务与 UAV 共线且相邻（合并明显省路），断言并入同一 UAV 且相邻输出
3. `test_cw_payload_capacity`：载荷超限场景（两任务各 3kg 且都最近于同架 max_payload=5 的 UAV）→ 断言 `solve()` 返回该 UAV 有 2 条独立路线（合并被容量阻止），且两任务均被分配
4. `test_cw_range_capacity`：`uav_max_ranges` 很小时不合并，任务保持单点路线
5. `test_cw_to_individual`：编码正确（每基因位 = 任务所属 UAV）
6. `test_cw_via_service`：`allocate(algorithm="cw")` 可跑通；`test_cw_listed_in_algorithms`：列表含 `cw`
7. `test_cw_empty_inputs`：空输入边界
8. `test_de_warm_start_seeds_population`：固定 seed，`_init_population()[0] == warm_start`
9. `test_de_warm_start_best_not_worse`：`solve()` 的 `best_cost <= evaluate_constrained(warm_start)`（精英保留保证）
10. `test_de_warm_start_invalid`：长度错/值域错 → ValueError
11. 回归：现有 37 个测试全部通过（含 `_common` 抽取后的 DE 代价矩阵测试）

## 6. 错误处理

- 空输入（无 UAV 或无任务）：`([], [t.id for t in tasks])`，同现有算法
- `warm_start` 非法：ValueError，同 DE 现有参数校验风格
- `uav_max_ranges` 校验：同 DE 现有规则（长度、正值）

## 7. 涉及文件清单

| 文件 | 动作 |
|---|---|
| `src/algorithms/task_allocation/_common.py` | 新增 — 公共常量与代价/航程工具 |
| `src/algorithms/task_allocation/clarke_wright.py` | 新增 — CW 求解器 + 适配函数 |
| `src/algorithms/task_allocation/differential_evolution.py` | 修改 — import 公共模块 + warm_start |
| `src/algorithms/task_allocation/__init__.py` | 修改 — 注册 `cw` |
| `tests/test_task_allocation.py` | 修改 — 新增 CW 与 warm_start 测试 |
| `README.md`（后端） | 修改 — 内置算法表增加 `cw` 行 |
