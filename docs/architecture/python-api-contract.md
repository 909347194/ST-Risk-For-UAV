# Python 算法服务接口契约（Node ↔ Python）

> 适用范围：`apps/server/node-backend` 的 `AlgorithmClient`（唯一通信闸门）↔ `apps/server/python-fastapi-backend`。
> Python 侧实现者可直接照此实现；本契约以 **Python pydantic schema 为真相源**，Node 侧 zod 镜像。
> 生成时间：2026-10-19。设计背景见 [agent-architecture-node-landing.md](./agent-architecture-node-landing.md) §7.9。

---

## 0. 总纲

> **确定性算法 RPC**：`POST JSON 进 → 同步 JSON 出`。**状态码表达成败，body 表达结果**；不要 200 + 错误体混语义。

四条不可违背的原则：

1. **确定性**：同输入必同输出——禁止 LLM、禁止无种子随机（这是"算法可复现"的底线）
2. **无状态**：状态放 PostgreSQL/PostGIS，不放进程内存；一个请求 = 一次完整计算
3. **无解 ≠ 错误**：算法跑完但无可行方案是**领域事实**（200 + 空结果），不是异常
4. **JSON-safe**：numpy 类型转原生、严禁 NaN/Infinity（JS `JSON.parse` 会直接崩）

---

## 1. 请求规范（Node → Python）

- `POST`，`Content-Type: application/json`
- 可选请求头 **`X-Correlation-Id`**：= Node 侧 pi `toolCallId`，**请透传进 Python 日志**，用于「工具调用 ↔ WorkerTask ↔ 落库记录」全链路回放
- 算法名走显式参数 `algorithm`；不传 = 用 Python 端默认
- 超时是 **per-method** 的（见下表）；Node 侧超时会**直接断开连接**（`agent.abort()`），Python 侧要能容忍 client 中途断开（不崩、不泄漏 worker）

| 端点 | 方法 | 超时 | 用途 |
|---|---|---|---|
| `/api/v1/tasks/allocate` | POST | 30s | 任务分配（Hungarian/Auction） |
| `/api/v1/paths/plan` | POST | 30s | 航线规划（A-star/RRT） |
| `/api/v1/risk/assess` | POST | 10s | 风险评估 |
| `/api/v1/adaptability/evaluate` | POST | 10s | 适配评估 |
| `/api/v1/health` | GET | 10s | 健康检查 |
| `/api/v1/{module}/algorithms` | GET | 10s | 可用算法清单 |

---

## 2. 数据模型（真相源 = pydantic，Node zod 镜像）

```python
# Python: src/domain/models.py
class Position(BaseModel):
    x: float
    y: float
    z: float = 0.0

class UAV(BaseModel):
    id: str
    position: Position
    speed: float          # 最大速度 m/s, > 0
    max_payload: float    # 最大载荷 kg, >= 0
    battery: float        # 电池容量 Wh, > 0
    status: UAVStatus = UAVStatus.IDLE

class Task(BaseModel):
    id: str
    position: Position
    priority: TaskPriority = TaskPriority.MEDIUM
    payload_weight: float        # 所需载荷 kg, >= 0
    time_limit: float | None = None  # 时间限制 s, > 0

class TaskAllocation(BaseModel):
    uav_id: str
    task_id: str
    estimated_cost: float  # 预估代价, >= 0
```

Node 侧对应类型在 `services/python/python-client.ts`（`UavPayload / TaskPayload / TaskAllocationPayload`），字段名完全一致（snake_case）。

---

## 3. 端点契约

### 3.1 `POST /api/v1/tasks/allocate` — 任务分配

**请求**（= `AllocateRequest`）：

```jsonc
{
  "uavs":   [ { "id": "uav-1", "position": {"x":0,"y":0,"z":0}, "speed": 15,
                "max_payload": 2, "battery": 200, "status": "idle" } ],   // ≥1
  "tasks":  [ { "id": "t-1", "position": {"x":100,"y":50,"z":0},
                "priority": "medium", "payload_weight": 1.2, "time_limit": 600 } ],  // ≥1
  "algorithm": "hungarian",     // 可选，默认 hungarian
  "params": {}                  // 可选，算法参数
}
```

**成功响应 200**（= `AllocateResponse`）：

```jsonc
{
  "allocations": [ { "uav_id": "uav-1", "task_id": "t-1", "estimated_cost": 123.4 } ],
  "unassigned_tasks": ["t-9"],   // 无可行方案时 = 全部任务 ID（这是领域事实，不是错误）
  "algorithm_used": "hungarian"  // 必须回带：实际用了哪个算法（可追溯）
}
```

### 3.2 `POST /api/v1/paths/plan` — 航线规划

请求：`{ "uavId", "origin": Position, "destination": Position, "constraints"?, "algorithm"? }`
响应 200：`{ "path": [...航点], "algorithm_used": "astar" }`
（⚠️ 字段以 Python `PlanRequest/PlanResponse` 为准，实现后回填本节）

### 3.3 `POST /api/v1/risk/assess` — 风险评估

请求：`{ "uavId"?, "region"?, "snapshot"? }` → 响应 200：`{ "risk": ... }`
（⚠️ 同上，以 `RiskAssessRequest/RiskAssessResponse` 为准回填）

### 3.4 `POST /api/v1/adaptability/evaluate` — 适配评估

请求：`{ "uavId", "taskId" }` → 响应 200：`{ "adaptable": true, "score"?, "reasons"? }`
（⚠️ 同上，以 `AdaptabilityRequest/AdaptabilityResponse` 为准回填）

---

## 4. 错误契约（状态码语义）

| 场景 | HTTP 状态 | Node 翻译 | 调用方行为 |
|---|---|---|---|
| 参数校验失败 / 算法名不存在 | **400 / 422** | `HTTP_4xx, retryable:false` | throw 交还 LLM 换参数 |
| 算法内部异常 / 服务故障 | **5xx** | `HTTP_5xx, retryable:true` | 可重试 |
| Node 侧超时（连接断） | — | `TIMEOUT, retryable:true` | 可重试/换算法 |
| 网络不通 | — | `NETWORK, retryable:true` | 可重试 |
| 响应结构对不上 | — | `CONTRACT_MISMATCH, retryable:false` | 炸在边界 + 报警 |

- 错误体用 FastAPI 标准 `HTTPException(status_code=..., detail="...")`（Node 主要看状态码，detail 进日志）
- **禁止** 200 + 错误结构体；**禁止** 5xx 表达"无解"

---

## 5. 返回体硬要求

1. **snake_case 字段名，只增不改**：`unassigned_tasks`、`algorithm_used`、`uav_id` 等定了不许改名/改义（Node zod 会炸在边界）；演进只能加字段
2. **JSON-safe**（numpy 大坑）：`ndarray → tolist()`、`np.float32/64 → float()`、`np.int → int()`；**严禁 NaN/Infinity**（Python `json` 默认放行但 JS 解析崩；建议序列化时 `allow_nan=False` 自查）
3. **确定性**：`algorithm_used` 必须回带；同参数复算必须同结果
4. **重算法限时**：单请求内 **25s 限时**（client 超时 30s）；超时宁可返回"无解/部分"也别拖死

---

## 6. Python 端实现清单（checklist）

- [ ] 所有端点有 pydantic `request/response_model`（本契约的真相源）
- [ ] 确定性：纯算法，无 LLM / 无未固定种子随机
- [ ] 无状态：数据从请求体/DB 取，不存进程内存
- [ ] numpy → 原生类型 + 无 NaN
- [ ] CPU-bound 算法不堵事件循环：`def` 端点（线程池）或 ProcessPool
- [ ] 容忍 client 中途断连（超时/abort）
- [ ] 日志打 `X-Correlation-Id`
- [ ] 响应回带 `algorithm_used`（或等价字段）
- [ ] 算法清单端点 `GET /api/v1/{module}/algorithms` 暴露可用算法名
- [ ] "无解"用 200 + 空结果表达，不用 5xx

---

## 7. 版本与演进

- Contract 版本常量见 node 端 `contracts/version.ts`（`WORKER_CONTRACT_VERSION`），写入每个 `WorkerTask.schemaVersion`
- 破坏性变更（改字段名/语义）必须双方同步改：Python pydantic + Node zod（`services/python/python-client.ts`）+ 本文件，三处同一提交
