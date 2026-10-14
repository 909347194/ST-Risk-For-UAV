# ST-Risk UAV — Python FastAPI Backend

算法服务，负责路径规划、任务分配、风险评估等核心计算。

## 技术栈

| 项 | 技术 |
|---|------|
| 语言 | Python ≥ 3.12 |
| 框架 | FastAPI + Uvicorn |
| 数据校验 | Pydantic ≥ 2.0 |
| ORM | SQLAlchemy 2.0（异步）+ Alembic |
| 数据库 | PostgreSQL + PostGIS + pgvector |
| 测试 | pytest + httpx |
| 包管理 | uv |

## 快速开始

以下命令均在 `apps/server/python-fastapi-backend/` 目录下执行（`src.main` 使用绝对导入 `from src...`，在别的目录启动会 `ModuleNotFoundError`）。先 `uv venv` 建虚拟环境（生成 `.venv`）；激活后（Windows: `.venv\Scripts\activate`；POSIX: `source .venv/bin/activate`）可直接用 `uvicorn` / `pytest` / `ruff` / `alembic`；未激活时，把 `uvicorn` / `pytest` / `ruff` / `alembic` 换成 `.venv/Scripts/python.exe -m ...`（Windows）或 `.venv/bin/python -m ...`（POSIX）。

```bash
# 建虚拟环境（uv 0.12.x 下 uv sync 不可用，见下）
uv venv

# 安装运行时 + 开发依赖（含 pytest-asyncio），-e 可编辑安装
.venv/Scripts/python.exe -m pip install -e ".[dev]"
# 或（uv 直接装进当前 venv）：
uv pip install -e ".[dev]"
# 不要用 uv sync：uv.lock 未入库，且 [project.scripts] 的入口点不会被安装

# 启动服务（开发模式，reload）
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
# 或在 monorepo 根目录
pnpm run dev:py

# 测试
pytest tests/ -q

# Lint & 格式化
ruff check src/
ruff format src/
```

数据库迁移见下方「数据库」一节。服务启动后访问 http://localhost:8000/docs 查看 Swagger 文档。

## 架构

### 分层总览

```mermaid
graph TB
    subgraph 表现层
        R[api/v1/endpoints/]
    end
    subgraph 契约层
        S[schemas/]
    end
    subgraph 业务层
        SV[services/]
    end
    subgraph 领域层
        D[domain/]
    end
    subgraph 算法层
        A[algorithms/]
    end
    subgraph 数据访问层
        RE[repositories/]
    end
    subgraph 数据库层
        DB[db/ + db/models/]
    end
    subgraph 基础设施
        U[utils/]
    end

    R -->|调用| SV
    R -.->|使用| S
    SV -->|调用| A
    SV -->|使用| D
    RE -->|查询| DB
    SV -->|通过| RE
    A -->|使用| D
    RE -->|使用| D
    SV -->|使用| U
```

### 三层模型

```mermaid
graph LR
    A[API 模型<br>schemas/] -->|转换| B[领域模型<br>domain/]
    B -->|映射| C[ORM 模型<br>db/models/]
    D[repositories/] -->|桥接| B
    D -->|桥接| C
```

- **API 模型** (`schemas/`)：请求/响应 DTO，仅用于路由层
- **领域模型** (`domain/`)：业务实体，用于 services/algorithms
- **ORM 模型** (`db/models/`)：数据库表结构，SQLAlchemy 映射

### 目录结构

```
src/
├── main.py                            # 入口（lifespan 优雅启动/退出）
├── __init__.py
│
├── api/                               # 表现层
│   └── v1/
│       ├── api.py                     #   路由汇总注册
│       └── endpoints/
│           ├── common.py              #   GET /health, GET /algorithms
│           ├── deps.py                #   公共依赖注入
│           ├── uav_resource.py        #   ① 无人机资源管理
│           ├── task_adaptability.py   #   ② 任务适配评估
│           ├── risk_assessment.py     #   ③ 飞行风险评估
│           ├── task_allocation.py     #   ④ 任务分配
│           ├── route_planning.py      #   ⑤ 航线规划
│           └── flight_monitoring.py   #   ⑥ 飞行监控
│
├── schemas/                           # API 契约层
│   ├── uav_resource.py
│   ├── task_adaptability.py
│   ├── risk_assessment.py
│   ├── task_allocation.py
│   ├── route_planning.py
│   └── flight_monitoring.py
│
├── services/                          # 业务层
│   ├── uav_resource/service.py
│   ├── task_adaptability/service.py
│   ├── risk_assessment/service.py
│   ├── task_allocation/service.py
│   ├── route_planning/service.py
│   └── flight_monitoring/service.py
│
├── domain/                            # 领域层
│   ├── models.py                      #   实体
│   ├── enums.py                       #   枚举
│   └── exceptions.py                  #   异常
│
├── algorithms/                        # 算法层（可插拔注册表）
│   ├── registry.py                    #   统一注册表
│   ├── path_planning/
│   │   ├── astar.py                   #   A* 栅格搜索
│   │   └── rrt.py                     #   快速随机树
│   └── task_allocation/
│       ├── hungarian.py               #   匈牙利算法
│       └── auction.py                 #   拍卖算法
│
├── repositories/                      # 数据访问层
│   ├── base.py                        #   基础仓储
│   ├── uav_repo.py
│   ├── adaptability_repo.py
│   ├── flight_log_repo.py
│   └── risk_repo.py
│
├── db/                                # 数据库层
│   ├── engine.py                      #   SQLAlchemy 引擎
│   ├── base.py                        #   Base 声明
│   └── models/
│       ├── uav.py
│       ├── task.py
│       ├── flight_log.py
│       ├── allocation.py
│       └── risk_record.py
│
└── utils/                             # 工具层
    ├── config.py                      #   Settings（pydantic-settings）
    └── utils.py
```

### 各层职责

| 层 | 目录 | 职责 |
|---|------|------|
| 表现层 | `api/v1/endpoints/` | 路由处理器，HTTP 校验与响应格式化 |
| 契约层 | `schemas/` | API 请求/响应 Pydantic 模型 |
| 业务层 | `services/` | 业务编排，调用算法与仓储 |
| 领域层 | `domain/` | 实体、枚举、异常，零业务逻辑 |
| 算法层 | `algorithms/` | 纯算法实现，通过 registry 统一注册 |
| 数据访问层 | `repositories/` | 封装数据库 CRUD |
| 数据库层 | `db/` | 引擎、会话、ORM 模型 |
| 工具层 | `utils/` | 配置管理、通用工具函数 |

## API 端点

> 任务分配模块的完整接口文档（字段表、实测示例、算法参数、代价语义、已知限制）见
> **[docs/api/task-allocation.md](docs/api/task-allocation.md)**。下表仅为端点速查。

### 公共

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/algorithms` | 列出所有已注册算法 |

### ① 无人机资源管理 (`/uavs`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/uavs` | 注册无人机 |
| GET | `/uavs` | 获取无人机列表 |
| GET | `/uavs/{id}` | 获取单个无人机 |
| PATCH | `/uavs/{id}/status` | 更新无人机状态 |

### ② 任务适配评估 (`/adaptability`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/adaptability/evaluate` | 单架 UAV 适配评估 |
| POST | `/adaptability/batch` | 批量适配评估 |

### ③ 飞行风险评估 (`/risk`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/risk/assess` | UAV-Task 组合风险评估 |

### ④ 任务分配 (`/tasks`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/allocate` | 任务分配（支持多算法：hungarian / auction / cw / de） |
| GET | `/tasks/algorithms` | 列出可用的任务分配算法及其参数 |

### ⑤ 航线规划 (`/paths`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/paths/plan` | 航线规划 |
| GET | `/paths/algorithms` | 列出可用路径规划算法 |

### ⑥ 飞行监控 (`/monitoring`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/monitoring/snapshot` | 提交无人机健康快照 |
| GET | `/monitoring/overview` | 监控总览 |
| GET | `/monitoring/{uav_id}/track` | 获取飞行轨迹 |
| GET | `/monitoring/alerts` | 获取告警列表 |

## ORM 模型

共 10 张表，表结构全部由 Alembic 迁移管理（见下方「数据库」）。

每张表的完整**列定义、索引、写入/读取路径与 psql 速查**见 **[docs/database-schema.md](docs/database-schema.md)**；下方 ER 图仅为速览。

```mermaid
erDiagram
    UAVModel {
        string id PK "表 uavs；写入方：将来 Node"
        geometry position "POINT_Z (PostGIS)"
        float speed
        float max_payload
        float battery
        string status
    }
    TaskModel {
        string id PK "表 tasks；写入方：将来 Node"
        geometry position "POINT_Z (PostGIS)"
        string priority
        float payload_weight
        float time_limit
        string status
    }
    AdaptabilityResultModel {
        integer id PK "表 adaptability_results；写入方：Python"
        string uav_id
        string task_id
        boolean capable
        float score
        jsonb reasons
    }
    RiskRecordModel {
        integer id PK "表 risk_records；写入方：Python"
        string uav_id
        string task_id
        string risk_level
        float collision_risk
        float weather_risk
        float battery_risk
        float overall_score
        jsonb details
    }
    PathPlanModel {
        integer id PK "表 path_plans；写入方：Python"
        string uav_id
        string task_id
        string algorithm
        jsonb waypoints
        float total_distance
        float estimated_time
    }
    AllocationRunModel {
        uuid id PK "表 allocation_runs；写入方：Python"
        string algorithm
        jsonb params
        integer assigned_count
        integer unassigned_count
        float duration_ms
    }
    AllocationItemModel {
        integer id PK "表 allocation_items；写入方：Python"
        uuid run_id FK
        string uav_id
        string task_id
        float estimated_cost
    }
    FlightSnapshotModel {
        integer id PK "表 flight_snapshots；写入方：Python"
        string uav_id
        float ts "仿真时间戳（秒）"
        geometry position "POINT_Z (PostGIS)"
        float battery_remaining
        boolean is_anomaly
        jsonb anomaly_reasons
    }
    FlightAlertModel {
        integer id PK "表 flight_alerts；写入方：Python"
        string uav_id
        string message
    }
    FlightLogModel {
        string id PK "表 flight_logs；写入方：Python（暂无写入方）"
        string uav_id "逻辑引用 uavs.id"
        geometry track "LINESTRING Z (PostGIS)"
        vector embedding "pgvector 128 维"
        datetime start_time
        datetime end_time
        float total_distance
    }

    AllocationRunModel ||--o{ AllocationItemModel : "run_id"
```

- `uavs`：写入方是**将来接入的 Node 后端**。Node 尚未接库，本轮暂由 Python 的 `/uavs` 端点代写，Node 就绪后 Python 退化为只读。
- `tasks`：写入方同样是**将来接入的 Node 后端**，Python 目前只读、无写入方。
- 其余 8 张表：**Python 写入**。其中 `flight_logs` 当前暂无写入方（表与列已建好，等「飞行会话」概念落地再接入）。
- `uav_id` / `task_id` 列目前是逻辑引用，除 `allocation_items.run_id` 外没有数据库外键约束。

## 内置算法

| 类别 | 算法 | 说明 | 适用场景 |
|------|------|------|----------|
| 路径规划 | `astar` | A* 栅格搜索 | 静态已知环境，最优路径 |
| 路径规划 | `rrt` | 快速随机树 | 复杂障碍物环境，高维空间 |
| 任务分配 | `hungarian` | 匈牙利算法 | 最优一对一匹配，小规模 |
| 任务分配 | `auction` | 拍卖算法 | 分布式竞价，大规模动态场景 |

算法通过 `algorithms/registry.py` 统一注册，可插拔扩展。

## 开发新接口

以「② 任务适配评估」模块为例。

### 流程

```mermaid
flowchart TD
    A[1. 定义领域模型] --> B[2. 定义 Schema]
    B --> C[3. 实现 Service]
    C --> D[4. 实现 Repository]
    D --> E[5. 编写路由]
    E --> F[6. 注册路由]
    F --> G[7. 编写测试]
    G --> H[8. 验证]

    style A fill:#e1f5fe
    style B fill:#e1f5fe
    style C fill:#fff3e0
    style D fill:#fff3e0
    style E fill:#e8f5e9
    style F fill:#e8f5e9
    style G fill:#fce4ec
    style H fill:#fce4ec
```

### 请求流转

```mermaid
sequenceDiagram
    participant Client
    participant Endpoint as endpoint
    participant Schema as schema
    participant Service as service
    participant Repo as repository
    participant DB as db

    Client->>Endpoint: POST /api/v1/adaptability/evaluate
    Endpoint->>Schema: 校验请求体 (AdaptabilityRequest)
    Schema-->>Endpoint: Pydantic 模型
    Endpoint->>Service: evaluate(uav, task)
    Service->>Repo: get_uav(uav_id)
    Repo->>DB: SELECT
    DB-->>Repo: ORM 对象
    Repo-->>Service: Domain 对象
    Service-->>Endpoint: AdaptabilityResult
    Endpoint->>Schema: 包装响应
    Schema-->>Client: JSON
```

### Step 1 — 定义领域模型

```python
# domain/models.py
class AdaptabilityResult(BaseModel):
    uav_id: str
    task_id: str
    capable: bool
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
```

### Step 2 — 定义 Schema

```python
# schemas/task_adaptability.py
class AdaptabilityRequest(BaseModel):
    uav_id: str
    task: Task
    min_battery_reserve: float = Field(default=0.2, ge=0, le=1)

class AdaptabilityResponse(BaseModel):
    result: AdaptabilityResult
```

### Step 3 — 实现 Service

```python
# services/task_adaptability/service.py
def evaluate(uav: UAV, task: Task, min_battery_reserve: float = 0.2) -> AdaptabilityResult:
    # 载荷检查、电量检查、航程检查...
    return AdaptabilityResult(uav_id=uav.id, task_id=task.id, capable=True, ...)
```

### Step 4 — 实现 Repository

```python
# repositories/uav_repo.py
class UAVRepository(InMemoryRepository[UAV, str]):
    def find_by_status(self, status: str) -> list[UAV]:
        return [u for u in self._store.values() if u.status == status]
```

### Step 5 — 编写路由

```python
# api/v1/endpoints/task_adaptability.py
@router.post("/evaluate", response_model=AdaptabilityResponse)
async def evaluate_adaptability(req: AdaptabilityRequest) -> AdaptabilityResponse:
    result = service.evaluate(uav, req.task, req.min_battery_reserve)
    return AdaptabilityResponse(result=result)
```

### Step 6 — 注册路由

```python
# api/v1/api.py
api_v1_router.include_router(adapt_router, prefix="/adaptability", tags=["② 任务适配评估"])
```

### Step 7 — 编写测试

```python
# tests/test_task_adaptability.py
def test_evaluate_capable():
    uav = UAV(id="uav-1", position=Position(x=0, y=0), speed=10.0, max_payload=5.0, battery=100.0)
    task = Task(id="task-1", position=Position(x=50, y=50), payload_weight=1.0)
    result = evaluate(uav, task)
    assert result.capable is True
```

### Step 8 — 验证

```bash
pytest tests/test_task_adaptability.py -v
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
# 然后访问 http://localhost:8000/docs
```

### 涉及文件

| 步骤 | 文件 | 动作 |
|------|------|------|
| 1 | `domain/models.py` | 修改 — 添加领域实体 |
| 2 | `schemas/task_adaptability.py` | 新增 — Request/Response |
| 3 | `services/task_adaptability/service.py` | 新增 — 业务逻辑 |
| 4 | `repositories/uav_repo.py` | 修改 — 添加查询方法 |
| 5 | `api/v1/endpoints/task_adaptability.py` | 新增 — 路由 |
| 6 | `api/v1/api.py` | 修改 — 注册路由 |
| 7 | `tests/test_task_adaptability.py` | 新增 — 测试用例 |

---

## 内置算法

| 类别 | 算法 | 说明 | 适用场景 |
|------|------|------|----------|
| 路径规划 | `astar` | A* 栅格搜索 | 静态已知环境，最优路径 |
| 路径规划 | `rrt` | 快速随机树 | 复杂障碍物环境，高维空间 |
| 任务分配 | `hungarian` | 匈牙利算法 | 最优一对一匹配，小规模 |
| 任务分配 | `auction` | 拍卖算法 | 分布式竞价，大规模动态场景 |
| 任务分配 | `de` | 离散差分进化 | 多机多任务，多约束场景 |
| 任务分配 | `cw` | Clarke-Wright 节约算法 | 构造启发式，多机多任务初始解 / DE 热启动 |

## 配置

通过环境变量或 `.env` 文件配置，前缀 `UAV_`：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `UAV_DEBUG` | `false` | 调试模式 |
| `UAV_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/st_risk` | 数据库连接（异步） |
| `UAV_DEFAULT_GRID_RESOLUTION` | `1.0` | 默认栅格分辨率 (m) |
| `UAV_RISK_COLLISION_THRESHOLD` | `0.7` | 碰撞风险阈值 |
| `UAV_RISK_WEATHER_THRESHOLD` | `0.6` | 气象风险阈值 |
| `UAV_RISK_BATTERY_THRESHOLD` | `0.8` | 电量风险阈值 |
| `UAV_MIN_BATTERY_RESERVE` | `0.2` | 最低电量保留比例 |

`.env` 读取顺序：仓库根 `.env` 与后端目录 `.env` 都会被加载，**后端目录的 `.env` 优先**。

## 持久化开关

| 变量 | 取值 | 默认 | 说明 |
|------|------|------|------|
| `UAV_REPOSITORY_BACKEND` | `memory` / `db` | `memory` | `memory` = 内存仓储，无需数据库即可启动；`db` = PostgreSQL（需先建库并迁移） |
| `UAV_PERSIST_RESULTS` | `on` / `off`（布尔，也接受 `true` / `false`） | `on` | 算法结果是否写入结果表；`off` 时四个算法端点（适配评估 / 风险评估 / 航线规划 / 任务分配）跳过写库 |

- `UAV_PERSIST_RESULTS` 只影响结果表（`allocation_runs` / `allocation_items` / `adaptability_results` / `risk_records` / `path_plans`）；`memory` 模式本身就不落库，故该开关在 `memory` 下无额外效果。
- `uavs` 与监控快照的写入不受 `UAV_PERSIST_RESULTS` 影响，随 `UAV_REPOSITORY_BACKEND` 切换走内存或 PostgreSQL。

## 数据库

Python 后端连库使用异步 DSN，配置项为 `UAV_DATABASE_URL`（`postgresql+asyncpg://...`）。Alembic 迁移与运行时读取同一份配置（`alembic/env.py` 调 `get_settings()`），不会出现「应用连 A 库、迁移连 B 库」。

```bash
# 1. 先建库（示例：本机 PostgreSQL；库名按 UAV_DATABASE_URL 中的名称）
createdb -U postgres st_risk
# 库需要 PostGIS + pgvector 扩展；在仓库根目录执行：
psql -U postgres -d st_risk -f infra/db/init.sql
# （Docker 环境当前镜像不含 PostGIS，限制见该文件头部说明）

# 2. 在仓库根 .env 或后端目录 .env 中设置连接串：
#    UAV_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/st_risk
#    并把 UAV_REPOSITORY_BACKEND 设为 db

# 3. 再迁移到最新版本
alembic upgrade head
```

日常迁移操作：

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "描述"

# 回滚一步
alembic downgrade -1
```

## 依赖

### 运行时

- fastapi ≥ 0.115, uvicorn[standard] ≥ 0.30
- pydantic ≥ 2.0, pydantic-settings ≥ 2.0
- sqlalchemy[asyncio] ≥ 2.0, asyncpg ≥ 0.30
- geoalchemy2 ≥ 0.15（PostGIS）
- pgvector ≥ 0.3（向量搜索）
- alembic ≥ 1.14

### 开发

- pytest ≥ 8.0, httpx ≥ 0.27
- ruff ≥ 0.5
