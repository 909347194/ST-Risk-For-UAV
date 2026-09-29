# 任务分配算法接口文档

> 版本：v1.0 | 日期：2026-09-29
> 分支：`feat/python-api-backend`
> 覆盖范围：`src/algorithms/task_allocation/` 全部算法，及其在 `src/api/v1/` 的 HTTP 封装

本文档面向**调用方**（前端、AI Agent、其他服务），说明如何通过 HTTP 接口使用任务分配算法。
文末另附 Python 层直调接口，供服务内部或脚本使用。

> **分支范围提示**：本分支的任务分配层**不含充电/补给规划**，**不含统筹自动选型**。
> 充电层在 `feat/energy`，`/tasks/solve` 统筹端点在 `feat/solver`。

---

## 一、概览

### 1.1 分层与调用链

```
HTTP 请求
   ↓
src/api/v1/endpoints/task_allocation.py   表现层 — 路由、HTTP 状态码映射
   ↓
src/services/task_allocation/service.py   业务层 — 取算法、透传 params
   ↓
src/algorithms/registry.py                算法注册表 — 按 (category, name) 取函数
   ↓
src/algorithms/task_allocation/**         算法层 — 纯计算，不感知 HTTP
```

- 算法经 `registry.register(...)` 注册，端点无需感知具体实现。
- 业务层只做 `get_algorithm(category, name)` + 把 `params` 展开为关键字参数：
  `algo_fn(uavs, tasks, **(params or {}))`。

### 1.2 基础信息

| 项 | 值 |
|---|---|
| Base URL | `http://localhost:8000/api/v1` |
| 请求/响应格式 | `application/json` |
| 路径前缀 | **所有接口都在 `/api/v1` 下**（健康检查是 `/api/v1/health`，不是 `/health`） |
| 交互式文档 | `http://localhost:8000/docs`（Swagger UI）与 `/redoc`，均为 FastAPI 默认路径 |

### 1.3 算法清单

| 名称 | 类型 | 分配粒度 | 产出补给计划 | 适用规模 |
|---|---|---|---|---|
| `hungarian` | 精确（穷举） | **一对一** | 否 | 极小规模（见 §4.1 警告） |
| `auction` | 启发式（竞价） | **一对一** | 否 | 中小规模 |
| `cw` | 构造启发式 | **一机多任务** | 否 | 多机多任务 |
| `de` | 进化算法 | **一机多任务** | 否 | 多机多任务、多约束 |

---

## 二、通用数据模型

定义于 `src/domain/models.py`，多接口复用。

### Position — 三维坐标

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `x` | float | ✅ | — | X 坐标 (m) |
| `y` | float | ✅ | — | Y 坐标 (m) |
| `z` | float | ❌ | `0.0` | Z 坐标 / 高度 (m) |

### UAV — 无人机

| 字段 | 类型 | 必填 | 默认 | 约束 | 说明 |
|---|---|---|---|---|---|
| `id` | string | ✅ | — | — | 唯一标识 |
| `position` | Position | ✅ | — | — | 当前位置（作为路线起点） |
| `speed` | float | ✅ | — | `> 0` | 最大速度 (m/s)，参与 DE 的飞行时间与 deadline 计算 |
| `max_payload` | float | ✅ | — | `>= 0` | 最大载荷 (kg)，CW 容量约束 |
| `battery` | float | ✅ | — | `> 0` | 电池容量 (Wh)，用于推导最大航程 |
| `status` | enum | ❌ | `"idle"` | — | `idle` \| `assigned` \| `in_flight` \| `returning` \| `maintenance` \| `offline` |

### Task — 任务

| 字段 | 类型 | 必填 | 默认 | 约束 | 说明 |
|---|---|---|---|---|---|
| `id` | string | ✅ | — | — | 唯一标识 |
| `position` | Position | ✅ | — | — | 目标位置 |
| `priority` | enum | ❌ | `"medium"` | — | `low` \| `medium` \| `high` \| `urgent` |
| `payload_weight` | float | ✅ | — | `>= 0` | 所需载荷 (kg) |
| `time_limit` | float \| null | ❌ | `null` | `> 0` | 时间限制 (s)，**仅 DE 使用** |

**优先级权重**（`_common.PRIORITY_WEIGHT`，参与代价矩阵）：

| 优先级 | `low` | `medium` | `high` | `urgent` |
|---|---|---|---|---|
| 权重 | 1.0 | 1.5 | 2.0 | 3.0 |

### TaskAllocation — 分配结果项

| 字段 | 类型 | 说明 |
|---|---|---|
| `uav_id` | string | 无人机 ID |
| `task_id` | string | 任务 ID |
| `estimated_cost` | float (`>= 0`) | 预估代价。**语义随算法变化，见 §六** |

---

## 三、HTTP 接口

### 3.1 GET /api/v1/algorithms

列出**全部**已注册算法（含路径规划），每项带 `category` 字段。

```json
[
  {
    "name": "hungarian",
    "description": "匈牙利算法 — 最优一对一匹配，适合任务数≈无人机数的场景",
    "params_schema": null,
    "category": "task_allocation"
  }
]
```

### 3.2 GET /api/v1/tasks/algorithms

只返回任务分配算法（4 个），**不含** `category` 字段。

`params_schema` 描述该算法 `params` 可接受的键、类型、默认值，可直接驱动前端表单；
值为 `null` 表示无可调参数（如 `hungarian`）。

### 3.3 POST /api/v1/tasks/allocate

由调用方**显式指定** `algorithm`。

#### 请求体

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `uavs` | UAV[] | ✅ | — | 至少 1 架 |
| `tasks` | Task[] | ✅ | — | 至少 1 个 |
| `algorithm` | string | ❌ | `"hungarian"` | `hungarian` \| `auction` \| `cw` \| `de` |
| `params` | object \| null | ❌ | `null` | 算法参数，键见 §五。**未知键会被 `**kwargs` 静默吸收** |

#### 响应体

| 字段 | 类型 | 说明 |
|---|---|---|
| `allocations` | TaskAllocation[] | 分配结果 |
| `unassigned_tasks` | string[] | 未能分配的任务 ID |
| `algorithm_used` | string | 等于请求的 `algorithm` |

> `algorithm_used` 直接回显请求值，不做校验回写；若算法内部逻辑变化，此字段不会反映。

#### 示例：四种算法同一组输入

**请求**（`algorithm` 依次换成四个值）：

```json
{
  "uavs": [
    {"id": "uav-1", "position": {"x": 0, "y": 0}, "speed": 15.0, "max_payload": 5.0, "battery": 300.0},
    {"id": "uav-2", "position": {"x": 50, "y": 0}, "speed": 12.0, "max_payload": 3.0, "battery": 200.0}
  ],
  "tasks": [
    {"id": "task-1", "position": {"x": 100, "y": 100}, "priority": "high",   "payload_weight": 2.0},
    {"id": "task-2", "position": {"x": 120, "y": 60},  "priority": "medium", "payload_weight": 1.5}
  ],
  "algorithm": "hungarian"
}
```

**响应 `200`**（实测，`estimated_cost` 注意各算法口径不同）：

`hungarian`：

```json
{
  "allocations": [
    {"uav_id": "uav-1", "task_id": "task-1", "estimated_cost": 282.842712474619},
    {"uav_id": "uav-2", "task_id": "task-2", "estimated_cost": 138.29316685939332}
  ],
  "unassigned_tasks": [],
  "algorithm_used": "hungarian"
}
```

`auction`：

```json
{
  "allocations": [
    {"uav_id": "uav-1", "task_id": "task-1", "estimated_cost": 141.4213562373095},
    {"uav_id": "uav-2", "task_id": "task-2", "estimated_cost": 92.19544457292888}
  ],
  "unassigned_tasks": [],
  "algorithm_used": "auction"
}
```

`cw`：

```json
{
  "allocations": [
    {"uav_id": "uav-1", "task_id": "task-2", "estimated_cost": 201.24611797498108},
    {"uav_id": "uav-2", "task_id": "task-1", "estimated_cost": 223.60679774997897}
  ],
  "unassigned_tasks": [],
  "algorithm_used": "cw"
}
```

`de`（`params: {"seed": 42}`）：

```json
{
  "allocations": [
    {"uav_id": "uav-2", "task_id": "task-2", "estimated_cost": 138.29316685939332},
    {"uav_id": "uav-2", "task_id": "task-1", "estimated_cost": 89.44271909999159}
  ],
  "unassigned_tasks": [],
  "algorithm_used": "de"
}
```

> 对比可见：`hungarian`/`auction` 给 `task-1` 的代价是 `distance × 2.0`（high 权重），
> 而 `auction` 报的是**纯距离**；`cw`/`de` 报的是**逐段距离**。详见 §六。

#### 错误

| 状态码 | 触发条件 | 实际 detail |
|---|---|---|
| 400 | 算法名不存在 | `未知算法: nope，可用: ['hungarian', 'auction', 'de', 'cw']` |
| 400 | 算法参数非法（`pop_size` 过小、`warm_start` 长度错、`uav_max_ranges` 含非正值等） | 校验信息原文，如 `pop_size 必须 >= 4（变异需 3 个互异候选个体），当前: 3` |
| 422 | 请求体不符合 schema：`uavs`/`tasks` 为空数组、`speed <= 0`、`battery <= 0`、缺必填字段等 | pydantic 标准错误体 |

---

## 四、算法详解

### 4.1 hungarian — 匈牙利算法

- **模块**：`src/algorithms/task_allocation/hungarian.py`
- **定位**：一对一指派，任务数 ≈ 无人机数，求综合代价最小
- **分配粒度**：一对一（每架 UAV 至多 1 个任务）

**代价定义**：`distance(uav, task) × PRIORITY_WEIGHT[task.priority]`

**实现说明（重要）**：文件内注释写的是「简化版匈牙利算法（穷举，适合小规模）」——
它用 `itertools.permutations` **枚举全排列**取最小代价，而非 O(n³) 的匈牙利算法。
因此复杂度是 **O(n!)**，`n = max(N_uav, N_task)`。

实测耗时（本机）：

| 规模 | 耗时 |
|---|---|
| 4 机 4 任务 | 0.1 ms |
| 6 机 6 任务 | 0.5 ms |
| 7 机 7 任务 | 2.9 ms |
| 8 机 8 任务 | 24.6 ms |
| 9 机 9 任务 | 228 ms |
| **3 机 10 任务** | **1.3 s** |
| **2 机 11 任务** | **14.3 s** |
| **5 机 11 任务** | **19.4 s** |

> ⚠️ **注意非对称陷阱**：耗时取决于 `max(N_uav, N_task)` 而非任务数。
> 即使只有 3 架无人机，只要有 10 个任务就会卡 1.3 秒，11 个任务接近 15 秒，
> 12 个任务将达到分钟级。**任务数 > 9 时请改用 `cw` 或 `de`。**

**参数**：无（`params_schema` 为 `null`）

```python
hungarian_allocate(uavs: list[UAV], tasks: list[Task], **kwargs)
    -> tuple[list[TaskAllocation], list[str]]
```

### 4.2 auction — 拍卖算法

- **模块**：`src/algorithms/task_allocation/auction.py`
- **定位**：分布式竞价，逐轮为未分配任务找最高出价 UAV
- **分配粒度**：一对一

**机制**：每轮对每个未分配任务计算各空闲 UAV 的
`bid = distance × PRIORITY_WEIGHT - price[task]`，取最大者为中标者，
并令 `price[task] += best_bid × 0.1`（价格递增）。无空闲 UAV 时任务进入未分配。

**参数**：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `max_iterations` | int | `100` | 最大迭代轮数 |

```python
auction_allocate(uavs, tasks, max_iterations: int = 100, **kwargs)
    -> tuple[list[TaskAllocation], list[str]]
```

> **注意**：`estimated_cost` 报的是**纯 `distance`，不含优先级权重** —— 与 `hungarian` /
> `cw` / `de` 口径不一致（详见 §六）。竞价本身用了权重，但输出代价没用。

### 4.3 cw — Clarke-Wright 节约算法

- **模块**：`src/algorithms/task_allocation/clarke_wright/`
- **定位**：构造启发式，秒级出多机多任务解；也是 DE 热启动个体的来源
- **分配粒度**：一机多任务（含任务访问顺序）
- **模型**：**开放路线**变体（无返程段），与 DE 适应度模型一致

**子模块分工**：

| 文件 | 职责 |
|---|---|
| `solver.py` | `ClarkeWrightSolver` 主循环 + `clarke_wright_allocate` 入口 |
| `capacity.py` | 航程 / 载荷可行性检查（`feasible`）与构造后修复（`rebalance`） |
| `encoding.py` | 路线逐段代价（`route_segment_costs`）、转 DE 个体（`to_individual`） |
| `clarke_wright.py` | 兼容旧导入路径的转发入口 |

**算法流程**：

1. 初始：每个任务一条单点路线，挂到最近的 UAV。
2. 迭代：贪心选取**最大正节约值**的合并对，节约值
   `s = cost(depot, i) + cost(depot, j) - cost(i, j)`（`i` 为路线 a 尾、`j` 为路线 b 头），
   要求合并后仍满足容量约束。
3. 修复：`rebalance` 把超容 UAV 路线末尾任务移交给"代价增量最小且不超容"的目标，
   并记录 `last_moved_from` 防止来回搬运，最多 `n_task` 轮。

**容量约束**（按 UAV 汇总，非按单条路线）：

| 约束 | 条件 |
|---|---|
| 航程 | 全部路线总航程 ≤ `uav_max_ranges[uav]` |
| 载荷 | 全部任务总载荷 ≤ `uav.max_payload` |

> 单点路线**不校验自身可行性** —— 保证每个任务至少被分配到某架 UAV。

**参数**：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `uav_max_ranges` | float[] \| null | `null` | 每机最大航程 (m)，长度必须等于 UAV 数且各项 `> 0` |
| `energy_per_meter` | float | `0.1` | 能耗率 (Wh/m)，缺省航程 = `battery / energy_per_meter` |

```python
clarke_wright_allocate(uavs, tasks, uav_max_ranges=None, energy_per_meter=0.1, **kwargs)
    -> tuple[list[TaskAllocation], list[str]]
```

### 4.4 de — 离散差分进化

- **模块**：`src/algorithms/task_allocation/differential_evolution/`
- **定位**：多机多任务、多约束场景的主力算法
- **分配粒度**：一机多任务
- **参考**：樊国政等《基于改进差分进化算法的同构无人机任务分配》；
  Zhao et al., *Acta Automatica Sinica*, 2012, 38(12): 2038-2048.

**子模块分工**：

| 文件 | 职责 |
|---|---|
| `config.py` | `DEConfig` 超参数 + 命名常量（惩罚与行为系数单一来源）+ `validate` |
| `encoding.py` | 整数编码 ↔ 分配方案、最近邻排序、逐段代价 |
| `population.py` | 种群初始化（随机 / 贪心扰动 / 热启动） |
| `operators.py` | 自适应 F/CR、变异、交叉、修复（纯函数） |
| `fitness.py` | 基础适应度 / 约束感知适应度 |
| `solver.py` | `DiscreteDESolver` 主循环 + `de_allocate` 入口 |

**编码约定**：

```
个体 = [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]
长度 = 任务数；第 i 个基因 = 执行任务 i 的 UAV 编号，值域 [0, N_uav)
```

- **解码**：先按基因分组，再用**最近邻贪心**排定每架 UAV 的任务顺序。
- **修复**：连续空间变异结果经 `round → clip(0, n_uav-1)` 回到合法整数基因型。
- **编码互逆**：`encode({uav_id: [task_id...]})` ↔ `decode(individual)`；
  编码输入必须覆盖全部任务，否则抛 `ValueError`。

**适应度**（`evaluate_constrained`，默认实际使用的口径）：

```
fitness = α·Σ(path_cost) + β·max_flight_time + γ·penalty_weight·Σ(violations)
```

| 约束 | 违反度量 |
|---|---|
| 最大航程 | `(path_cost - max_range) / max_range` |
| 任务 deadline | 累计到达时刻 > `time_limit` 时 `+0.5` / 任务 |
| 负载均衡 | `var(各机任务数) × 0.01` |

> 另有 `evaluate`（基础适应度 = 总路径代价 + 超航程固定惩罚 `10000`），
> 但主循环用的是 `evaluate_constrained`。

**改进点**：

1. **自适应 F/CR**：`F = F_init × (1 - 0.6 × progress)`（0.9 → 0.36，探索转开发）；
   `CR = CR_init + 0.4 × progress`（0.5 → 0.9）。
2. **精英引导变异**：以 `elite_guide_prob` 概率用 `DE/current-to-best/1`，否则 `DE/rand/1`。
3. **启发式初始化**：`heuristic_ratio` 比例个体由贪心解加随机翻转（`FLIP_PROBABILITY=0.1`）得来。
4. **热启动**：传入 `warm_start` 后，种群 `[0]` 即该个体，其余按比例扰动 + 随机。
5. **可复现**：`seed` 经 `np.random.default_rng` 固定。

**参数**：

| 参数 | 类型 | 默认 | 约束 | 说明 |
|---|---|---|---|---|
| `pop_size` | int | `50` | `>= 4` | 种群规模（变异需 3 个互异候选） |
| `generations` | int | `100` | — | 进化代数 |
| `F_init` | float | `0.9` | — | 差分权重初值 |
| `CR_init` | float | `0.5` | — | 交叉率初值 |
| `elite_guide_prob` | float | `0.3` | — | 精英引导变异概率 |
| `heuristic_ratio` | float | `0.2` | `(0, 1]` | 启发式初始化占比 |
| `uav_max_ranges` | float[] \| null | `null` | 长度 = UAV 数，各项 `> 0` | 每机最大航程 (m) |
| `energy_per_meter` | float | `0.1` | — | 能耗率 (Wh/m) |
| `penalty_weight` | float | `500.0` | — | 约束罚分权重（**不在 `params_schema` 中，但可直传**） |
| `alpha` | float | `1.0` | — | 路径代价权重（**同上，未广告**） |
| `beta` | float | `0.5` | — | 最大飞行时间权重（**同上，未广告**） |
| `gamma` | float | `1.0` | — | 罚分整体权重（**同上，未广告**） |
| `seed` | int \| null | `null` | — | 随机种子（复现用） |
| `warm_start` | int[] \| null | `null` | 长度 = 任务数，各值 ∈ `[0, N_uav)` | 热启动个体 |

```python
de_allocate(uavs, tasks, pop_size=50, generations=100, F_init=0.9, CR_init=0.5,
            elite_guide_prob=0.3, heuristic_ratio=0.2, uav_max_ranges=None,
            energy_per_meter=0.1, penalty_weight=500.0, seed=None, warm_start=None,
            **kwargs) -> tuple[list[TaskAllocation], list[str]]
```

**统计信息**：`DiscreteDESolver.solve()` 返回 `(best_allocation, stats)`，
`stats` 含 `best_cost` / `convergence_gen` / `total_generations` / `time_seconds` /
`history_min` / `history_avg`。**但 `de_allocate` 丢弃了 `stats`，HTTP 层拿不到。**

---

## 五、参数速查

### 全部可用参数（按算法）

| 参数 | hungarian | auction | cw | de |
|---|---|---|---|---|
| `max_iterations` | — | ✅ 100 | — | — |
| `pop_size` | — | — | — | ✅ 50 |
| `generations` | — | — | — | ✅ 100 |
| `F_init` / `CR_init` | — | — | — | ✅ 0.9 / 0.5 |
| `elite_guide_prob` | — | — | — | ✅ 0.3 |
| `heuristic_ratio` | — | — | — | ✅ 0.2 |
| `uav_max_ranges` | — | — | ✅ null | ✅ null |
| `energy_per_meter` | — | — | ✅ 0.1 | ✅ 0.1 |
| `penalty_weight` | — | — | — | ⚠️ 500.0（未广告） |
| `alpha` / `beta` / `gamma` | — | — | — | ⚠️ 1.0 / 0.5 / 1.0（未广告） |
| `seed` | — | — | — | ✅ null |
| `warm_start` | — | — | — | ✅ null |

✅ = 在 `params_schema` 中广告　⚠️ = 可传但未列入 `params_schema`　— = 不适用

> **未广告参数**（`penalty_weight` / `alpha` / `beta` / `gamma`）可以正常传入生效，
> 但 `GET /tasks/algorithms` 不会告诉你它们存在。调整适应度权重时需要直接传。

### 最大航程推导

`cw` 与 `de` 共用 `_common.derive_uav_ranges`：

```
uav_max_ranges[i] = battery[i] / energy_per_meter      # energy_per_meter > 0
                  = +inf                                # energy_per_meter <= 0
```

显式传入 `uav_max_ranges` 时优先使用，但会校验：
长度必须等于 UAV 数、各项必须 `> 0`，否则抛 `ValueError`。

---

## 六、`estimated_cost` 语义对照

**这是最容易踩的坑：四个算法的 `estimated_cost` 口径互不相同，不可跨算法比较。**

| 算法 | `estimated_cost` 含义 | 含优先级权重 | 顺序 |
|---|---|---|---|
| `hungarian` | `distance × PRIORITY_WEIGHT` | ✅ | 无（一对一） |
| `auction` | **纯 `distance`** | ❌ | 无（一对一） |
| `cw` | 逐段 `distance`（首段自 UAV 位置起） | ❌ | CW 路线访问顺序 |
| `de` | 逐段 `distance`（最近邻排序后） | ❌ | 最近邻顺序 |

> `hungarian` 之外三者都不含优先级权重；只有 `hungarian` 的代价反映优先级。
> 若前端要展示"统一口径的距离"，请自行用 `uav.position` 与 `task.position` 重算，
> 不要直接读 `estimated_cost`。

---

## 七、一对一 vs 一机多任务

`hungarian` / `auction` 是**一对一**映射（每架 UAV 至多接 1 个任务），
`cw` / `de` 是**一机多任务**（每架 UAV 可接多个并给出顺序）。

实测（2 架 UAV、5 个任务）：

| 算法 | 分配条数 | 覆盖任务 | 未分配 |
|---|---|---|---|
| `hungarian` | 2 | task-1, task-2 | **task-3, task-4, task-5** |
| `auction` | 2 | task-1, task-2 | **task-3, task-4, task-5** |
| `cw` | 5 | 全部 | 无 |
| `de` | 5 | 全部 | 无 |

> ⚠️ **在 `N_uav < N_task` 的场景下误用 `hungarian`/`auction` 会导致大量任务静默未分配。**
> 多机多任务场景请用 `cw` 或 `de`。
> 反之 `cw`/`de` 的 `unassigned_tasks` **恒为空**（编码覆盖全部任务）。

---

## 八、错误处理

### 8.1 现状

| 状态码 | 触发条件 |
|---|---|
| 200 | 成功 |
| 400 | 算法名不存在（`AlgorithmNotFoundError`）或**算法参数非法**（`ValueError`） |
| 422 | 请求体不符合 schema（缺字段、类型错误、`uavs`/`tasks` 为空、`speed <= 0` 等） |

### 8.2 两类 400 的区分

端点把算法层的两类异常统一映射为 400，`detail` 直接携带原始消息：

```python
# 算法不存在、算法参数非法 — 均为客户端错误，须回传 400 而非 500
except (AlgorithmNotFoundError, ValueError) as e:
    raise HTTPException(status_code=400, detail=str(e))
```

| 类别 | 抛出点 | `detail` 形态 |
|---|---|---|
| 算法名不存在 | `registry.get_algorithm` | `未知算法: nope，可用: [...]` |
| 参数非法 | `_common.derive_uav_ranges`（`cw`/`de`）、`DEConfig.validate`（`de`） | 校验信息原文，见下表 |

实测以下输入均返回 **400 + JSON**，`detail` 为对应校验信息
（`tests/test_api_task_allocation.py` 中 8 条用例逐条覆盖）：

| 输入 | `detail` |
|---|---|
| `de` `pop_size=3` | `pop_size 必须 >= 4（变异需 3 个互异候选个体），当前: 3` |
| `de` `heuristic_ratio=0` | `heuristic_ratio 必须在 (0, 1] 区间，当前: 0.0` |
| `de` `heuristic_ratio=1.5` | `heuristic_ratio 必须在 (0, 1] 区间，当前: 1.5` |
| `de` `warm_start` 长度 ≠ 任务数 | `warm_start 长度必须等于任务数 (2)，当前: 1` |
| `de` `warm_start` 值越界 | `warm_start 基因值必须在 [0, 2) 区间` |
| `de`/`cw` `uav_max_ranges` 长度 ≠ UAV 数 | `uav_max_ranges 长度必须等于 UAV 数 (2)，当前: 1` |
| `de`/`cw` `uav_max_ranges` 含非正值 | `uav_max_ranges 各项必须 > 0，当前: [0.0, 100.0]` |

> 回归测试：`tests/test_api_task_allocation.py` 逐条锁定上述映射，
> 防止参数校验重新退化为 500。

**对调用方的建议**：仍建议调用前按 §五 的参数约束自行校验，以获得更早、更明确的反馈；
但 400 的 `detail` 已可直接用于定位是哪个参数不合法。

---

## 九、已知限制

| # | 限制 | 影响 |
|---|---|---|
| 1 | **`hungarian` 是穷举排列实现，O(n!)** | `max(N_uav, N_task) > 9` 时耗时从百毫秒级跳到秒级乃至分钟级 |
| 2 | **`hungarian` 忽略 `Task.time_limit`** | 时间窗只在 `de` 的适应度中生效，指派场景下可能给出超时指派 |
| 3 | **`auction` 的 `estimated_cost` 不含优先级权重** | 与其他算法口径不一致，跨算法比较无意义 |
| 4 | **`auction` 无优先级相关行为保证** | 一轮一轮贪心，且 UAV 一旦中标即退出后续竞价 |
| 5 | **未广告参数**（`alpha`/`beta`/`gamma`/`penalty_weight`） | 存在且生效，但 `params_schema` 未列出，容易被忽略 |
| 6 | **`cw` / `de` 的 `unassigned_tasks` 恒为空** | 编码覆盖全部任务，容量超限靠罚分/修复缓解，不会显式报告"装不下" |
| 7 | **`de_allocate` 丢弃求解统计** | `convergence_gen` / `history_min` 等 HTTP 层拿不到 |
| 8 | **无充电/补给规划** | 本分支不含能量层；`cw`/`de` 只按航程上限约束，不规划中途充电 |
| 9 | **无统筹自动选型** | 必须显式指定 `algorithm`；`/tasks/solve` 在 `feat/solver` 分支 |

---

## 十、Python 层直调接口

服务内部或脚本可直接调用算法层，绕开 HTTP。

### 10.1 经注册表（推荐）

```python
from src.algorithms import get_algorithm, AlgorithmCategory

fn = get_algorithm(AlgorithmCategory.TASK_ALLOCATION, "de")
allocations, unassigned = fn(uavs, tasks, seed=42, generations=200)
```

### 10.2 直接导入

```python
from src.algorithms.task_allocation.hungarian import hungarian_allocate
from src.algorithms.task_allocation.auction import auction_allocate
from src.algorithms.task_allocation.clarke_wright import ClarkeWrightSolver, clarke_wright_allocate
from src.algorithms.task_allocation.differential_evolution import DiscreteDESolver, de_allocate
```

**四个入口函数统一签名**（便于替换）：

```python
fn(uavs: list[UAV], tasks: list[Task], **params) -> tuple[list[TaskAllocation], list[str]]
```

**需要求解细节时用 Solver 类**：

```python
from src.algorithms.task_allocation.differential_evolution import DiscreteDESolver

solver = DiscreteDESolver(uavs, tasks, generations=200, seed=42)
best_allocation, stats = solver.solve()     # {uav_idx: [task_idx...]}, 含收敛统计

# CW → DE 热启动的衔接（DE 侧）
cw = ClarkeWrightSolver(uavs, tasks)
warm = cw.to_individual()                    # 路线 → DE 整数编码
solver = DiscreteDESolver(uavs, tasks, warm_start=warm, seed=42)
```

`encode` / `decode` 为互逆操作：

```python
ind = solver.encode({0: [0, 2], 1: [1]})     # {uav_id: [task_id]} → 整数个体
plan = solver.decode(ind)                    # 整数个体 → {uav_id: [task_id]}（最近邻排序）
```

---

## 十一、完整调用示例

```bash
# 启动服务（须在后端根目录，模块路径是 src.main:app）
cd apps/server/python-fastapi-backend
uv run uvicorn src.main:app --host 127.0.0.1 --port 8000

# 1) 列出任务分配算法及其参数
curl http://localhost:8000/api/v1/tasks/algorithms

# 2) 多机多任务（CW）
curl -X POST http://localhost:8000/api/v1/tasks/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "uavs": [
      {"id":"uav-1","position":{"x":0,"y":0},"speed":15,"max_payload":5,"battery":300},
      {"id":"uav-2","position":{"x":50,"y":0},"speed":12,"max_payload":3,"battery":200}
    ],
    "tasks": [
      {"id":"t1","position":{"x":100,"y":100},"priority":"high","payload_weight":2},
      {"id":"t2","position":{"x":120,"y":60},"priority":"medium","payload_weight":1.5},
      {"id":"t3","position":{"x":80,"y":-40},"priority":"low","payload_weight":1}
    ],
    "algorithm": "cw",
    "params": {"uav_max_ranges": [5000, 4000], "energy_per_meter": 0.1}
  }'

# 3) 多约束进化解（DE，固定种子可复现）
curl -X POST http://localhost:8000/api/v1/tasks/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "uavs": [
      {"id":"uav-1","position":{"x":0,"y":0},"speed":15,"max_payload":5,"battery":300}
    ],
    "tasks": [
      {"id":"t1","position":{"x":100,"y":0},"payload_weight":1,"time_limit":20},
      {"id":"t2","position":{"x":200,"y":0},"payload_weight":1,"time_limit":40}
    ],
    "algorithm": "de",
    "params": {"pop_size": 30, "generations": 50, "seed": 42}
  }'
```

---

## 十二、相关文档

| 文档 | 说明 |
|---|---|
| [差分进化分配设计](../superpowers/specs/2026-09-04-de-task-allocation-design.md) | DE 编码、适应度、算子设计 |
| [CW 热启动设计](../superpowers/specs/2026-09-07-clarke-wright-warm-start-design.md) | CW → DE 热启动衔接 |
| [CW 容量再平衡设计](../superpowers/specs/2026-09-07-cw-capacity-rebalance-design.md) | `rebalance` 容量修复 |
| [无人机分配场景全集](../../../../../docs/architecture/algorithms/task-allocation/无人机分配场景全集.md) | 40 个分配场景 |
| [算法选型思考](../../../../../docs/architecture/algorithms/task-allocation/算法选型思考.md) | 选型依据 |
| [任务分配算法方案](../../../../../docs/architecture/algorithms/task-allocation/任务分配算法方案.md) | 算法方案综述 |
