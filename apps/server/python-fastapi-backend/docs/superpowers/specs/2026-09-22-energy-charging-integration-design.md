# 补给(充电)分配 — energy 模块与全链路接入设计文档

日期:2026-09-22
分支:feat/python-api-backend
上游设计:`docs/architecture/algorithms/task-allocation/无人机补给分配设计.md`(commit 08fec35)
验证背景:全部算法 API 已验证可调用(见 scripts/verify_algorithm_apis.py);发现端点未捕获 ValueError → 500 的问题,本设计顺带修复。

## 1. 背景与目标

充电站引入后,任务分配从"带一次性容量约束"升级为"带逐段能量约束"的 E-VRP 变体:
可行性从二元判断变为"绕行 + 充电时间"的连续代价。按上游设计采用**外层分配 + 内层充电**分层结构:

- 外层(CW / DE)主体不动,负责"谁做哪些任务、以什么顺序";
- 内层(新模块 `energy/`)负责"给定序列,何时去哪个站充多少",返回真实代价(时间/能耗)回代外层判定。

本次交付:模型 + 矩阵扩展 + energy 模块(贪心 A + DP E)+ CW/DE 嵌入 + API 与注册表改造,一次性打通端到端。

## 2. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 代码位置 | `src/algorithms/task_allocation/energy/` 子目录(遵循 clarke_wright/、differential_evolution/ 的模块拆分模式) |
| 内层策略 | 贪心(策略 A)+ DP(策略 E)都做;DE 直接用 v2 内层最优法,不做 v1 惩罚过渡 |
| CW 内层策略 | `greedy`(构造期快检 + 构造后修复,保持构造速度) |
| DE 内层策略 | `dp`(适应度用 DP 真实时间,含充电) |
| hungarian/auction | 本 round 不动(拍卖能量扩展属上游设计 §7.2 中期) |
| 路线语义 | 沿用现状开放路线(不回基地),终点 = 最后一个任务,终点到达电量也要求 ≥ σ |
| σ 缺省值 | 有 stations 且 sigma 未指定时,每机取 `0.1 × battery`(与上游 §4 例子 B=100, σ=10 一致) |
| 能量修不好的处理 | CW 任务仍保留(覆盖全部任务的设计语义不变),该机 recharge_plan 标记 `feasible=False` |
| UAV 级 energy_per_meter | 不做(YAGNI,全局参数够用) |
| 返回签名 | cw/de 入口函数改为 3 元组 `(allocations, unassigned, plans)`;hungarian/auction 保持 2 元组;service 保留 `allocate`(2 元组)供既有调用方,新增 `allocate_with_plans`(3 元组)供端点使用 |
| 向后兼容 | stations 缺省(空列表)时行为与输出内容不变;既有测试仅 cw/de 入口直接解包处做 2→3 机械修改,其余一律不改动 |

## 3. 文件与改动清单

### 3.1 数据模型 `src/domain/models.py`

新增:

```python
class ChargingStation(BaseModel):
    """充电站"""
    id: str
    position: Position
    power: float = Field(gt=0, description="充电功率 (W)")
    slots: int = Field(default=1, ge=1, description="同时可服务无人机数")
```

UAV 不加 `energy_per_meter` 字段。

### 3.2 矩阵扩展 `src/algorithms/task_allocation/_common.py`

保留 `build_cost_matrix`(优先级加权,现有求解器继续使用)。新增:

```python
def build_distance_matrix(uavs, tasks, stations) -> np.ndarray:
    """纯物理距离矩阵(无优先级权重),供能耗计算"""

def build_energy_matrix(uavs, tasks, stations, energy_per_meter: float) -> np.ndarray:
    """能耗矩阵 (Wh) = 距离 × energy_per_meter"""
```

索引约定:`0..N_uav-1` = UAV,`N_uav..N_uav+N_task-1` = 任务,`N_uav+N_task..` = 充电站。
`derive_uav_ranges` 保留,仅作快速剪枝。

### 3.3 新模块 `src/algorithms/task_allocation/energy/`

#### `plan.py` — RechargePlan 数据类

```python
@dataclass
class ChargeEvent:
    station_id: str
    charge_wh: float          # 充电量
    arrive_time: float        # 到站时刻 (s)
    leave_time: float         # 离站时刻 (s)

@dataclass
class RechargePlan:
    uav_id: str
    node_seq: list[int]           # 扩展节点序列(任务/站交替,矩阵索引)
    charges: list[ChargeEvent]
    total_time: float             # 飞行 + 充电总时间 (s)
    total_energy: float           # 总飞行能耗 (Wh)
    arrival_times: list[float]    # 与 node_seq 对齐的逐节点到达时刻 (s),DE deadline 检查用
    feasible: bool
```

#### `feasibility.py`

```python
def check_energy_feasibility(seq, e_matrix, B, sigma) -> tuple[bool, list[float]]:
    """逐段 SoC 跟踪(不插站):返回 (可行?, 各节点到达电量)。对应上游 §4.1
    判定:每节点到达电量 ≥ σ(含终点)。"""
```

#### `greedy.py` — 策略 A(阈值触发 + 最近站 + 充满)

```python
def greedy_insert_stations(seq, e_matrix, stations, B, sigma) -> RechargePlan | None:
    """若到达下一节点后电量 < σ,插入绕行代价最小(次级标准:功率大)的站并充满;
    连站都够不到 → 返回 None(交外层重分配)。对应上游 §4.2 / §6.3 伪代码。"""
```

#### `dp.py` — 策略 E(离散 DP 最优充电)

```python
def optimal_charging_dp(seq, e_matrix, stations, B, sigma, delta=None) -> RechargePlan:
    """电量按 delta(缺省 B/10)离散化,状态 (节点, 电量档);
    转移 1 直飞(到达 ≥ σ)、转移 2 绕站后充至任意档;代价 = 飞行时间 + 充电时间;
    终点取电量 ≥ σ 的最优档回溯。对应上游 §4.3 / §6.3 伪代码。"""
```

统一约定(实现必须遵守):

- `seq: list[int]` = 矩阵节点索引列表,**首元素为该机 UAV 起点下标**,后续为任务节点;
- 飞行时间 = 段距离 / `speed`(speed 由外层作为参数传入,不放在 seq 里);
- `stations` 参数 = 站点矩阵索引列表(energy 层不关心站点对象细节,只按索引取功率);
- energy 层仅在 `stations` 非空时启用;`sigma` 仅在 energy 层激活时生效;
- σ 未显式指定时按 `0.1 × B` 推导,发生在 energy 函数内部(调用方不必传)。

### 3.4 CW 嵌入 `src/algorithms/task_allocation/clarke_wright/`

1. **构造期快检**(改 `capacity.feasible` / `solver._feasible` 调用处,合并循环逻辑不动):
   现有"总航程 ≤ max_range 且总载荷 ≤ max_payload"保留作快剪枝;其后增加能量检查:
   - 直飞 `check_energy_feasibility` 可行 → 放行;
   - 不可行但 `greedy_insert_stations` 可行 → 放行(否则好解被误杀);
   - 否则拒绝合并。
   节约值公式 `c(depot,i) + c(depot,j) − c(i,j)` 不变(基于优先级加权距离,保持构造速度)。
   `ClarkeWrightSolver` 构造时在 `build_cost_matrix` 之外增建距离/能耗矩阵与站点索引
   (stations 为空时能耗层整体关闭,走现状路径)。

2. **构造后 `_energy_repair`**(`solve()` 末尾,`_rebalance` 之后):
   - 对每条路线跑 `greedy_insert_stations` 生成 RechargePlan;
   - 返回 None 的路线:把末尾任务移交给"能量余量最大且不超容"的 UAV(沿用 rebalance
     的移交思路与 `last_moved_from` 防回移),重试插入,循环 ≤ N_task 轮;
   - 仍修不好:该机 plan 标记 `feasible=False`,任务保留。

### 3.5 DE 嵌入 `src/algorithms/task_allocation/differential_evolution/`

- `fitness.evaluate_constrained` 增加可选参数(stations / sigma / energy_matrix / 缓存):
  每机序列跑 `optimal_charging_dp`,**用真实总时间(含充电)替换 path_cost 与 flight_time**
  代入 `α·Σt + β·max t`;DP 不可行 → 沿用 RANGE_PENALTY 模式加能量惩罚项。
- **stations 非空时禁用约束 1(总航程 ≤ max_range)**:DP 的逐段能量可行性已覆盖
  能量约束,且硬航程上限会把"超预算但可充电修复"的路线误杀(上游 §4.5 的核心结论);
  stations 为空时保持现状(约束 1 生效)。
- `DiscreteDESolver` 持有 `_dp_cache: dict[(uav_idx, tuple(seq)), RechargePlan]`,
  代价矩阵静态,整个进化过程复用。
- 默认 `energy_strategy="dp"`;`"greedy"` 也可用;`"none"` = 现状行为(无 stations 时自动等价)。
- `solve()` 主循环流程不变;`de_allocate` 返回分配不变,附加生成每机 RechargePlan。

### 3.6 API 与注册表

- `src/schemas/task_allocation.py`:
  - `AllocateRequest` += `stations: list[ChargingStation] = []`(直接复用领域模型,与 uavs/tasks 一致)、`sigma: float | None = None`、`energy_strategy: str = "auto"`("auto" = cw→greedy, de→dp, 其余 none)。
  - `AllocateResponse` += `recharge_plans: list[UAVRechargePlanOut]`;**每条路线一条**(CW 一机可能多条路线,DE 每机一条),字段:uav_id、charges、total_time、total_energy、feasible;无 stations 时为 `[]`。
- `src/services/task_allocation/service.py`:新增 `allocate_with_plans()`(3 元组,供端点)与私有 `_run()`;
  `allocate()` 保持 2 元组签名不变(既有调用方/测试零影响);hungarian/auction 已有 `**kwargs`,无需改。
- `src/algorithms/task_allocation/__init__.py`:cw/de 的 params_schema 增加
  `sigma`、`energy_strategy(greedy|dp|none)` 条目,`stations` 说明注为请求体字段。
- `src/api/v1/endpoints/task_allocation.py`:捕获 `ValueError` → `HTTPException(400)`(修复验证时发现的 500)。

## 4. 测试计划

### 4.1 新增 `tests/test_energy.py`(上游 §4 演算为基准)

| 用例 | 断言 |
|---|---|
| 无充电可行性 | `D→T1→T2→T3→E` 逐段 SoC 在 T2 处 < σ → `check_energy_feasibility` 返回 False |
| 贪心修复 | 单站 C(P=700W):扩展序列 `D→T1→C(充70)→T2→T3→E`,总时间 520s(±浮点容差) |
| DP 与贪心一致 | 单站 + 带 σ 最优 = 充满 → DP 结果同为 520s |
| DP 部分充电边界 | 充 60 → 468.6s 更短但终点电量 0 < σ → 被拒(不产生该计划) |
| 站不可达 | 站位置使"到站电量 < σ" → 贪心返回 None |
| σ 语义 | 未指定时按 `0.1 × B` 推导;终点电量 ≥ σ 检查生效 |

### 4.2 增补 `tests/test_task_allocation.py`

- cw 带 stations:返回 allocations 全量 + recharge_plans 每机一个、feasible=True、含充电事件;
- de 带 stations:跑通(DP 缓存生效,冒烟级性能断言);
- **向后兼容**:不带 stations 时与现状输出一致,现有全部用例不改动通过。

### 4.3 API 级用例

- POST `/api/v1/tasks/allocate` 带 stations/sigma/energy_strategy → 200,响应含 recharge_plans;
- 非法参数(uav_max_ranges 长度不符)→ 400(不再是 500);
- GET `/tasks/algorithms` → cw/de 的 params_schema 含 sigma / energy_strategy。

## 5. 范围外(明确不做)

- 站容量与排队(slots 仅预留字段)、动态重规划、拍卖能量扩展(上游 §7.2/§7.3);
- 策略 B/C/D(恰好补能/充满/机会充电)不作为独立选项,DP 已在最优档上自然覆盖部分充电;
- 能耗模型精度升级(载荷/风/速度曲线,上游 §7.3)。

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| DE 每代全量 DP 的性能 | `_dp_cache` 按 (uav_idx, seq) 缓存;默认 delta=B/10;性能冒烟用例守护 |
| 能量修不好时输出不可行方案 | response 明确 `feasible=False`,不静默吞掉;调用方可见 |
| 贪心与 DP 结果不一致 | 测试 4.1 用单站场景锚定两者一致;多站差异是已知的设计特性(上游 §5.6) |
| 现有调用方受影响 | stations 缺省 → 全部走现状路径;现有测试不动 |
