# ST-Risk UAV Service — Python FastAPI Backend

无人机任务分配与路径规划服务，基于 FastAPI 构建，采用分层架构。

## 技术栈

- **语言**：Python ≥ 3.12
- **Web 框架**：FastAPI + Uvicorn
- **包管理**：uv
- **数据校验**：Pydantic ≥ 2.0
- **数据库**：SQLAlchemy 2.0（异步）+ Alembic 迁移
- **测试**：pytest + httpx

## 快速开始

```bash
# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装依赖
uv sync

# 安装开发依赖
uv sync --extra dev

# 数据库迁移
alembic upgrade head

# 启动服务
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 运行测试
uv run pytest tests/ -v
```

服务启动后访问 http://localhost:8000/docs 查看 Swagger 文档。

## 架构

```
src/
├── main.py                  # 入口
├── db/                      # 数据库层：引擎、会话、ORM 模型
│   ├── engine.py            #   异步引擎 + SessionLocal
│   ├── base.py              #   DeclarativeBase
│   └── models/              #   ORM 模型（映射到数据库表）
├── models/                  # 数据模型层：核心实体、枚举、异常（Pydantic）
├── utils/                   # 通用工具层：配置管理、几何计算
├── algorithms/              # 算法层：统一注册表，可插拔算法实现
│   ├── path_planning/       #   A*, RRT
│   └── task_allocation/     #   匈牙利算法, 拍卖算法
├── repositories/            # 数据访问层：封装 CRUD（SQLAlchemy 异步实现）
├── services/                # 业务层：每个模块一个包
│   ├── uav_resource/        #   ① 无人机资源管理
│   ├── task_adaptability/   #   ② 任务适配评估
│   ├── risk_assessment/     #   ③ 飞行风险评估
│   ├── task_allocation/     #   ④ 任务分配
│   ├── route_planning/      #   ⑤ 航线规划
│   └── flight_monitoring/   #   ⑥ 飞行监控
├── schemas/                 # 契约层：Request / Response Pydantic 模型
└── routes/                  # 表现层：API 路由
```

### 依赖方向

```
Routes  →  Services  →  Algorithms  →  Models
  │           │
 Schemas   Repositories  →  DB (SQLAlchemy Async)
              │
           Utils
```

### 命名约定

| 目录 | 职责 |
|------|------|
| `db/` | 数据库层：异步引擎、会话工厂、ORM 模型定义 |
| `models/` | 领域模型（Pydantic 实体、枚举、异常），零业务逻辑 |
| `utils/` | 通用工具函数、配置管理 |
| `algorithms/` | 纯算法实现，通过 `registry` 统一注册 |
| `repositories/` | 数据访问接口，SQLAlchemy 异步 CRUD 实现 |
| `services/` | 业务编排，每个模块为一个包（`__init__.py` + `service.py`） |
| `schemas/` | API 请求/响应模型，仅定义契约 |
| `routes/` | HTTP 路由，处理请求校验和响应格式化 |

### 数据库

使用 SQLAlchemy 2.0 异步模式 + Alembic 管理迁移：

```python
# 异步引擎
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

engine = create_async_engine("sqlite+aiosqlite:///./data/uav.db")

# 异步会话
async_session = AsyncSession(engine)
```

**ORM 模型**定义在 `db/models/`，映射到数据库表。
**Pydantic 模型**定义在 `models/`，用于业务逻辑和 API 契约。
两层模型分离，通过 repositories 层桥接。

**Alembic 迁移**：

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1
```

## API 端点

### 公共

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/algorithms` | 列出所有已注册算法 |

### ① 无人机资源管理 `/api/v1/uavs`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/uavs` | 注册无人机 |
| GET | `/uavs` | 列出无人机（支持 `?status=idle` 过滤） |
| GET | `/uavs/{id}` | 查询单架无人机 |
| PATCH | `/uavs/{id}/status` | 更新状态 |
| DELETE | `/uavs/{id}` | 移除无人机 |
| GET | `/uavs/{id}/snapshot` | 获取健康快照 |

### ② 任务适配评估 `/api/v1/adaptability`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/adaptability/evaluate` | 单机适配评估 |
| POST | `/adaptability/batch` | 批量评估（按评分排序） |

### ③ 飞行风险评估 `/api/v1/risk`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/risk/assess` | 综合风险评估（碰撞/气象/电量） |

### ④ 任务分配 `/api/v1/tasks`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/allocate` | 执行任务分配 |
| GET | `/tasks/algorithms` | 列出可用分配算法 |

### ⑤ 航线规划 `/api/v1/paths`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/paths/plan` | 执行航线规划 |
| GET | `/paths/algorithms` | 列出可用规划算法 |

### ⑥ 飞行监控 `/api/v1/monitoring`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/monitoring/snapshot` | 提交健康快照（含异常检测） |
| GET | `/monitoring/track/{id}` | 获取飞行轨迹 |
| GET | `/monitoring/alerts/{id}` | 获取告警记录 |
| DELETE | `/monitoring/alerts/{id}` | 清除告警 |
| GET | `/monitoring/overview` | 监控总览 |

## 内置算法

### 路径规划

| 算法 | 说明 | 适用场景 |
|------|------|----------|
| `astar` | A* 栅格搜索 | 静态已知环境，最优路径 |
| `rrt` | 快速随机树 | 复杂障碍物环境，高维空间 |

### 任务分配

| 算法 | 说明 | 适用场景 |
|------|------|----------|
| `hungarian` | 匈牙利算法 | 最优一对一匹配，小规模 |
| `auction` | 拍卖算法 | 分布式竞价，大规模动态场景 |

## 配置

通过环境变量或 `.env` 文件配置，前缀 `UAV_`：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `UAV_DEBUG` | `false` | 调试模式 |
| `UAV_DATABASE_URL` | `sqlite+aiosqlite:///./data/uav.db` | 数据库连接（异步） |
| `UAV_DEFAULT_GRID_RESOLUTION` | `1.0` | 默认栅格分辨率 (m) |
| `UAV_RISK_COLLISION_THRESHOLD` | `0.7` | 碰撞风险阈值 |
| `UAV_RISK_WEATHER_THRESHOLD` | `0.6` | 气象风险阈值 |
| `UAV_RISK_BATTERY_THRESHOLD` | `0.8` | 电量风险阈值 |
| `UAV_MIN_BATTERY_RESERVE` | `0.2` | 最低电量保留比例 |

## 测试

```bash
uv run pytest tests/ -v
```

覆盖：路径规划、任务分配、资源管理、适配评估、风险评估、飞行监控。

## 依赖

### 运行时

- fastapi ≥ 0.115
- uvicorn[standard] ≥ 0.30
- pydantic ≥ 2.0
- pydantic-settings ≥ 2.0
- sqlalchemy[asyncio] ≥ 2.0
- aiosqlite ≥ 0.20
- alembic ≥ 1.14

### 开发

- pytest ≥ 8.0
- httpx ≥ 0.27
- ruff ≥ 0.5
