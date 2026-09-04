# 差分进化（DE）任务分配算法移植 — 设计文档

日期：2026-09-04
分支：feat/python-api-backend
参考实现：`D:\uav-planner\backend\app\algorithms\differential_evolution.py`

## 1. 背景与目标

将参考项目中的离散差分进化求解器移植到本项目 `src/algorithms/task_allocation/`，
作为第三种任务分配算法（与 hungarian、auction 并列），供 `POST /tasks/allocate` 通过
`algorithm="de"` 调用。

参考论文：樊国政等《基于改进差分进化算法的同构无人机任务分配》；
Zhao et al., Acta Automatica Sinica, 2012, 38(12): 2038-2048（约束感知适应度，Eq. 23）。

## 2. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 交付范围 | 完整移植 DE 分配（约束适应度、自适应参数、启发式初始化、收敛检测），不内置路径规划 |
| 数值依赖 | 引入 numpy（pyproject.toml 增加 `numpy>=1.26`） |
| 注册位置 | `task_allocation` 类别，注册名 `de`，文件在 `src/algorithms/task_allocation/` 下 |
| 代价函数 | `欧氏距离 × 优先级权重`（与 hungarian/auction 同一套 PRIORITY_WEIGHT） |
| 约束范围 | 3 类：最大航程、任务 deadline（Task.time_limit）、负载均衡。时序/时间窗省略 |
| 代码结构 | 类为核心（`DiscreteDESolver`）+ 薄适配注册函数（`de_allocate`），服务层/端点零改动 |

## 3. 文件与类结构

新增 `src/algorithms/task_allocation/differential_evolution.py`：

### DiscreteDESolver（参考代码 BaseSolver + ImprovedDESolver 合并）

合并理由：本项目没有 GA 等其他求解器共享 `BaseSolver`，两层继承是多余抽象；
方法名与逻辑与参考代码一一对应，便于对照论文。

构造参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `uavs` / `tasks` | — | 本项目 domain 模型 `UAV` / `Task` 列表 |
| `pop_size` | 50 | 种群规模 |
| `generations` | 100 | 进化代数 |
| `F_init` / `CR_init` | 0.9 / 0.5 | 差分权重 / 交叉率初值 |
| `elite_guide_prob` | 0.3 | 精英引导变异概率 |
| `heuristic_ratio` | 0.2 | 启发式初始化个体占比 |
| `uav_max_ranges` | None | 每机最大航程；缺省由 `battery / energy_per_meter` 推算 |
| `energy_per_meter` | 0.1 | 能耗率 (Wh/m)，与 task_adaptability 的估算一致 |
| `alpha` / `beta` / `gamma` | 1.0 / 0.5 / 1.0 | 适应度权重（参考 Eq. 23） |
| `penalty_weight` | 500.0 | 违反量惩罚系数 |
| `seed` | None | 随机种子（**新增**，参考代码无；保证实验可复现，内部用 `np.random.default_rng`） |

核心方法（忠实移植）：

- `_build_cost_matrix()`：`cost[i][j] = distance(i, j) × PRIORITY_WEIGHT[task.priority]`，对角线 0
- `decode(individual)`：整数编码（基因位 = 任务下标，取值 = UAV 下标）→ `{uav_idx: [task_idx...]}`，序列内最近邻排序
- `_init_population()`：`heuristic_ratio` 比例个体用贪心最近 UAV 构造 + 10% 随机翻转，其余随机
- `_adaptive_params(gen)`：`F = F_init × (1 - 0.6·progress)`（0.9→0.36），`CR = CR_init + 0.4·progress`（0.5→0.9）
- `_mutate()`：`DE/current-to-best/1`（概率 `elite_guide_prob`）否则 `DE/rand/1`
- `_crossover()`：二项式交叉 + `j_rand` 保证至少一维交叉
- `_repair()`：round → clip 到 `[0, N_uav-1]`
- `evaluate_constrained()`：`fitness = alpha·Σ路径代价 + beta·max飞行时间 + gamma·penalty_weight·Σ违反量`
- `solve()`：主循环（精英保留、贪婪选择）+ 收敛检测（`history_min` 间隔 5 代差值 < 0.01），
  返回 `(allocation: dict[int, list[int]], stats: dict)`
  stats 含 `best_cost / convergence_gen / time_seconds / history_min / history_avg`

### de_allocate 薄适配函数

```python
def de_allocate(uavs, tasks, **params) -> tuple[list[TaskAllocation], list[str]]
```

- 签名与 hungarian/auction 完全一致 → `services/task_allocation/allocate()` 零改动
- 内部实例化 `DiscreteDESolver` 并 `solve()`，按每机解码序列顺序扁平化为
  `list[TaskAllocation]`（**列表顺序即任务执行顺序**，按 uav_id 分组可还原序列）
- DE 整数编码天然覆盖全部任务，`unassigned` 恒为 `[]`
- 空输入（无 UAV 或无任务）返回 `([], [task.id for t in tasks])`，与现有算法一致
- 未知 kwargs 忽略（与 astar/rrt 的 `**kwargs` 风格一致）
- 需要完整 stats（论文实验）时直接实例化类调用 `solve()`，不经过注册函数

## 4. 约束适配（3 类）

| 参考代码约束 | 本项目映射 |
|---|---|
| ① 最大航程 | `path_cost > max_range` 时违反量 `(path_cost - max_range) / max_range`；`max_range` 来自 `uav_max_ranges` 参数或 `battery / energy_per_meter` |
| ② 飞行时间 | 参考代码的"时间 ≤ 航程/速度"在速度恒定时与①等价，省略；改用 `Task.time_limit` 作为 deadline：该任务累计到达时刻 > time_limit 时违反量 +0.5（仅对设置了 time_limit 的任务） |
| ③ 任务时序 | 领域模型不支持，省略 |
| ④ 时间窗 | 领域模型不支持，省略 |
| ⑤ 负载均衡 | `np.var(每机任务数) × 0.01`，同参考代码 |

## 5. 注册

`src/algorithms/task_allocation/__init__.py` 的 `_register()` 增加：

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

## 6. 服务层 / API 影响

零改动。验证方式：`POST /api/v1/tasks/allocate` body `"algorithm": "de"` 返回
`allocations + unassigned_tasks`；`GET /api/v1/tasks/algorithms` 自动列出 `de`。

## 7. 测试计划（先写测试，后实现）

在 `tests/test_task_allocation.py` 增加：

1. `test_de_basic`：2 机 3 任务，全部分配、无重复 (uav_id, task_id) 对、estimated_cost ≥ 0
2. `test_de_empty_inputs`：空 UAV / 空任务边界，返回形状正确
3. `test_de_cluster_reasonable`：两个任务簇明显靠近各自 UAV 时，用固定 seed 断言簇内任务归对应 UAV
4. `test_de_seed_reproducible`：同 seed 两次运行结果完全一致；不同 seed 结果可不同（不断言后者）
5. `test_de_interface_contract`：返回 `(list, list)` 且 unassigned 为空；服务层 `allocate(algorithm="de")` 路径可跑通
6. 回归：现有 14 个测试全部通过

## 8. 错误处理

- 空输入：`([], [task.id ...])`，同现有算法
- `Task.time_limit` 为 None 的任务跳过 deadline 约束
- `energy_per_meter <= 0` 时视为未提供航程约束（不做除零）
- 未知 kwargs：忽略（不抛 TypeError）

## 9. 依赖变更

`pyproject.toml`：`dependencies` 增加 `"numpy>=1.26"`，执行 `uv sync` 更新 lockfile。

## 10. 涉及文件清单

| 文件 | 动作 |
|---|---|
| `pyproject.toml` | 修改 — 增加 numpy |
| `src/algorithms/task_allocation/differential_evolution.py` | 新增 — 类 + 适配函数 |
| `src/algorithms/task_allocation/__init__.py` | 修改 — 注册 `de` |
| `tests/test_task_allocation.py` | 修改 — 新增 DE 测试 |
| `README.md`（后端） | 修改 — 内置算法表增加 `de` 行 |
