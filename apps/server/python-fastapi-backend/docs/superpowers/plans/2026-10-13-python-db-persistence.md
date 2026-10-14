# Python 后端持久化落地 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Python 后端从模块级内存仓储切换到 PostgreSQL，使算法产出与运行时数据可持久化、可查询。

**Architecture:** 仓储接口统一改为 async，保留内存实现（默认）用于无库开发与单测，新增 SQLAlchemy 实现，由工厂按 `UAV_REPOSITORY_BACKEND` 选择。表结构由 Alembic 统一管理，10 张表一次建齐。算法结果落库放在 endpoint 层，service 保持纯函数。

**Tech Stack:** FastAPI · SQLAlchemy 2.0 async · asyncpg · GeoAlchemy2 · pgvector · Alembic · pytest-asyncio · PostgreSQL 18.3（本机原生，含 PostGIS 3.6.2 与 pgvector）

## Global Constraints

- 工作目录：所有命令在 `apps/server/python-fastapi-backend` 下执行（`main.py` 用绝对导入 `from src.utils...`，在 `src/` 内启动会 `ModuleNotFoundError`）
- 解释器：`.venv/Scripts/python.exe`；测试 `pytest tests/ -q`；lint `ruff check src/`
- **不要用 `uv run dev` / `uv run test` / `uv run lint`** —— `[project.scripts]` 全部不可执行（值为 shell 字符串且项目无 `[build-system]`）
- 本机库：PostgreSQL 18.3 @ localhost:5432，PostGIS 3.6.2 ✅、pgvector ✅
- 数据库名：`st_risk`；扩展 `postgis`、`vector` 均由迁移创建，`CREATE EXTENSION` 需超级用户
- DDL 权威唯一归 Alembic；**Node 侧 Drizzle 本轮不动**
- 默认 `UAV_REPOSITORY_BACKEND=memory`、`UAV_PERSIST_RESULTS=on` —— 默认值必须保证无库环境下服务可启动、测试可跑
- 表归属：`uavs` / `tasks` 标注「将来 Node 写入、Python 只读」；其余 8 张表由 Python 写入
- 提交信息用中文，格式 `feat(python-db): ...` / `test(python-db): ...` / `docs(python-db): ...`

## 前置阻塞项

**Task 7（生成迁移）之前**必须先解决：`.env` 中的 `UAV_DATABASE_URL` 对本机 5432 认证失败（当前密码是照 Docker 容器配的），且 `st_risk` 库需已存在。Task 1~6 和 Task 8~13 不依赖数据库，可先行。

---

## 文件结构

**新建**

| 文件 | 职责 |
|---|---|
| `alembic.ini` · `alembic/env.py` · `alembic/script.py.mako` | 迁移配置（异步模板） |
| `alembic/versions/<rev>_initial_schema.py` | 初始迁移（含扩展与索引） |
| `src/db/models/allocation.py` | `AllocationRunModel` / `AllocationItemModel` |
| `src/db/models/adaptability.py` | `AdaptabilityResultModel` |
| `src/db/models/risk_record.py` | `RiskRecordModel` |
| `src/db/models/path_plan.py` | `PathPlanModel` |
| `src/db/models/monitoring.py` | `FlightSnapshotModel` / `FlightAlertModel` |
| `src/repositories/mappers.py` | 领域模型 ↔ ORM 模型互转 |
| `src/repositories/db/__init__.py` | DB 仓储包导出 |
| `src/repositories/db/uav_repo.py` | `UAVDbRepository` |
| `src/repositories/db/monitoring_repo.py` | `FlightLogDbRepository` |
| `src/repositories/db/allocation_repo.py` | `AllocationRunDbRepository` |
| `src/repositories/db/record_repo.py` | 适配/风险/航线三个扁平记录仓储 |
| `src/repositories/factory.py` | 按配置返回内存或 DB 实现 |
| `tests/conftest.py` | 异步 fixture |
| `tests/test_db_persistence.py` | 集成测试（`@pytest.mark.integration`） |

**修改**

| 文件 | 改动 |
|---|---|
| `pyproject.toml` | 加 `pytest-asyncio`、pytest 标记与 `addopts` |
| `src/utils/config.py` | 新增两项配置；修 `env_file` 路径 |
| `src/db/models/uav.py` · `task.py` | 加时间戳 / `status` / 归属标注 |
| `src/db/models/flight_log.py` | 加归属标注 |
| `src/db/models/__init__.py` | 导出全部 10 张表 |
| `src/repositories/base.py` | 接口改 async |
| `src/repositories/uav_repo.py` · `flight_log_repo.py` · `adaptability_repo.py` · `risk_repo.py` | 改 async、改走工厂 |
| `src/services/uav_resource/service.py` · `flight_monitoring/service.py` | 改 async |
| `src/api/v1/endpoints/*.py` | 加 `await`、结果落库、读端点 |
| `src/schemas/task_allocation.py` | 加 run 读端点 schema |
| `src/main.py` | 关闭时释放引擎 |
| `tests/test_services.py` | 异步化 |
| `infra/db/init.sql` · `.env.example` · `README.md` | 修正与文档 |

---

## Phase 1 — 测试与配置基础设施

### Task 1: 测试基础设施（pytest-asyncio）

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: 无
- Produces: `asyncio_mode = "auto"` 使后续所有 `async def test_*` 无需装饰器；`integration` 标记供 Task 10~13 使用

- [ ] **Step 1: 加依赖与 pytest 配置**

`pyproject.toml` 的 `[project.optional-dependencies] dev` 数组加入 `"pytest-asyncio>=0.24"`，并在文件末尾追加：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
# pytest-asyncio 1.x：循环作用域必须显式声明，否则 configure 阶段告警
# （未来版本默认值还会变）。function 级即可 —— 集成测试的引擎本来
# 就是每个用例各自创建、各自 dispose 的。
asyncio_default_fixture_loop_scope = "function"
asyncio_default_test_loop_scope = "function"
addopts = "-m 'not integration'"
markers = [
    "integration: 需要真实 PostgreSQL（PostGIS + pgvector）的集成测试",
]
```

- [ ] **Step 2: 安装依赖**

Run: `.venv/Scripts/python.exe -m pip install "pytest-asyncio>=0.24"`
Expected: `Successfully installed pytest-asyncio-...`

- [ ] **Step 3: 建 conftest.py**

`tests/conftest.py`：

```python
"""pytest 公共配置占位

asyncio_mode = "auto"（见 pyproject.toml）已接管 async 测试的循环管理，
无需任何 fixture。

注意：pytest-asyncio 1.0 起不再识别自定义 event_loop fixture（写成
死代码）；如需会话级循环，用 pyproject 里的 asyncio_default_*_loop_scope。
"""
```

- [ ] **Step 4: 验证既有测试仍全绿**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS，且输出里出现 `deselected` 为 0（此时还没有 integration 测试）

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "test(python-db): 引入 pytest-asyncio 与 pytest 配置"
```

---

### Task 2: 配置项扩展与 `.env` 路径修正

**Files:**
- Modify: `src/utils/config.py`

**Interfaces:**
- Consumes: 无
- Produces: `Settings.repository_backend: Literal["memory","db"]`、`Settings.persist_results: bool`（Task 11、12 使用）

**背景：** 现 `model_config` 的 `env_file=".env"` 相对 **cwd** 解析，而后端目录下没有 `.env`（只有仓库根有），导致按 README 在 backend 目录起服务时读不到任何配置、静默回落到默认值。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_config.py`：

```python
"""配置层契约"""

from pathlib import Path

from src.utils.config import Settings


def test_env_file_path_is_absolute_and_cwd_independent():
    """env_file 必须由模块位置推导，而不是相对 cwd"""
    env_files = Settings.model_config["env_file"]
    assert isinstance(env_files, (tuple, list)), "应为多文件元组"
    for f in env_files:
        assert Path(f).is_absolute(), f"{f} 不是绝对路径"


def test_repository_backend_defaults_to_memory():
    """默认必须是内存实现 —— 无库环境下服务要能起来"""
    assert Settings().repository_backend == "memory"


def test_persist_results_defaults_to_true():
    assert Settings().persist_results is True


def test_backend_root_env_is_last_priority():
    """后端自有 .env 优先级应高于仓库根 .env"""
    env_files = [Path(f) for f in Settings.model_config["env_file"]]
    assert env_files[-1].name == ".env"
    assert env_files[-1].parent.name == "python-fastapi-backend"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL —— `KeyError: 'env_file'`（当前是字符串）或 `AttributeError: repository_backend`

- [ ] **Step 3: 实现**

`src/utils/config.py` 改为：

```python
"""全局配置"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

# src/utils/config.py -> parents[2] = apps/server/python-fastapi-backend
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
# parents[5] = 仓库根 ST-Risk-For-UAV-1
_REPO_ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    """应用配置，优先读取环境变量"""

    app_name: str = "ST-Risk UAV Service"
    app_version: str = "0.1.0"
    debug: bool = False

    # 数据库
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/st_risk"

    # 存储后端：memory = 内存仓储（默认，无库可用）；db = PostgreSQL
    repository_backend: Literal["memory", "db"] = "memory"
    # 算法结果是否落库；off 时端点跳过写库（无库开发用）
    persist_results: bool = True

    # 路径规划默认参数
    default_grid_resolution: float = 1.0
    default_search_margin: float = 50.0

    # 风险评估阈值
    risk_collision_threshold: float = 0.7
    risk_weather_threshold: float = 0.6
    risk_battery_threshold: float = 0.8

    # 适配评估
    min_battery_reserve: float = 0.2  # 至少保留 20% 电量

    model_config = {
        "env_prefix": "UAV_",
        # 相对 cwd 解析会踩坑：按 README 在 backend 目录启动时读不到仓库根的 .env。
        # 改为按模块位置推导的绝对路径；后一个文件优先，故后端自有 .env 可覆盖根 .env。
        "env_file": (_REPO_ROOT / ".env", _BACKEND_ROOT / ".env"),
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

同时把 `pyproject.toml` 里 `pydantic-settings` 的依赖下限从 `>=2.0` 提到 `>=2.4`：`env_file` 接受路径元组需要 2.4+，旧下限会允许解析出 2.0~2.3 的坏版本。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: 4 passed

- [ ] **Step 5: 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/utils/config.py tests/test_config.py
git commit -m "feat(python-db): 新增仓储/落库配置项并修正 env_file 路径解析"
```

---

## Phase 2 — 数据模型与迁移

### Task 3: 补全 A 组主数据模型

**Files:**
- Modify: `src/db/models/uav.py`、`src/db/models/task.py`

**Interfaces:**
- Produces: `UAVModel`（新增 `created_at` / `updated_at`）、`TaskModel`（新增 `status` / `created_at` / `updated_at`）—— Task 7 的迁移与 Task 9 的映射层依赖这些列名

- [ ] **Step 1: 改写 uav.py**

```python
"""ORM 模型 — UAV 表（PostGIS 几何列）

表归属：**将来由 Node 后端写入，Python 只读**。
本轮 Node 侧尚未接库，Python 的 /uavs 端点暂时承担写入；待 Node 就绪后
Python 应退化为只读，不再提供写端点。
"""

from sqlalchemy import Column, String, Float, DateTime, func
from geoalchemy2 import Geometry

from src.db.base import Base


class UAVModel(Base):
    __tablename__ = 'uavs'

    id = Column(String, primary_key=True)
    position = Column(Geometry('POINT_Z', srid=4326), nullable=False)  # PostGIS 3D 点
    speed = Column(Float, nullable=False)
    max_payload = Column(Float, nullable=False)
    battery = Column(Float, nullable=False)
    status = Column(String, nullable=False, default='idle')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
```

- [ ] **Step 2: 改写 task.py**

```python
"""ORM 模型 — Task 表

表归属：**将来由 Node 后端写入，Python 只读**（同 uavs）。

time_limit 采用浮点：能无损容纳整数，反之会截断；与领域模型
Task.time_limit: float | None 一致。Node 侧 Drizzle 模型写的 integer
需要对齐到浮点。
"""

from sqlalchemy import Column, String, Float, DateTime, func
from geoalchemy2 import Geometry

from src.db.base import Base


class TaskModel(Base):
    __tablename__ = 'tasks'

    id = Column(String, primary_key=True)
    position = Column(Geometry('POINT_Z', srid=4326), nullable=False)
    priority = Column(String, nullable=False, default='medium')
    payload_weight = Column(Float, nullable=False)
    time_limit = Column(Float, nullable=True)
    status = Column(String, nullable=False, default='pending')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
```

- [ ] **Step 3: 验证模型可导入且列齐全**

Run: `.venv/Scripts/python.exe -c "from src.db.models import UAVModel, TaskModel; print(sorted(c.name for c in UAVModel.__table__.columns)); print(sorted(c.name for c in TaskModel.__table__.columns))"`
Expected: `['battery', 'created_at', 'id', 'max_payload', 'position', 'speed', 'status', 'updated_at']` 与 `['created_at', 'id', 'payload_weight', 'position', 'priority', 'status', 'time_limit', 'updated_at']`

- [ ] **Step 4: 提交**

```bash
git add src/db/models/uav.py src/db/models/task.py
git commit -m "feat(python-db): 补全 uavs/tasks 模型时间戳与 status 并标注归属"
```

---

### Task 4: 新增 B 组算法结果表模型

**Files:**
- Create: `src/db/models/allocation.py`、`src/db/models/adaptability.py`、`src/db/models/risk_record.py`、`src/db/models/path_plan.py`

**Interfaces:**
- Produces: `AllocationRunModel`、`AllocationItemModel`、`AdaptabilityResultModel`、`RiskRecordModel`、`PathPlanModel` —— Task 7 迁移与 Task 10 仓储依赖

- [ ] **Step 1: 建 allocation.py**

```python
"""ORM 模型 — 任务分配结果表（run + 明细两层）

表归属：**Python 写入**。

一次 /tasks/allocate 调用 = 一条 run；该次调用里的每条 uav→task 配对
= 一条 item。这样既能按 algorithm 分组横向比较各算法的指标，又能
回放具体分配方案。
"""

import uuid

from sqlalchemy import (Column, String, Integer, Float, DateTime,
                        ForeignKey, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.db.base import Base


class AllocationRunModel(Base):
    __tablename__ = 'allocation_runs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    algorithm = Column(String, nullable=False)
    params = Column(JSONB, nullable=True)
    uav_count = Column(Integer, nullable=False)
    task_count = Column(Integer, nullable=False)
    assigned_count = Column(Integer, nullable=False)
    unassigned_count = Column(Integer, nullable=False)
    unassigned_task_ids = Column(JSONB, nullable=False, default=list)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AllocationItemModel(Base):
    __tablename__ = 'allocation_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(UUID(as_uuid=True),
                    ForeignKey('allocation_runs.id', ondelete='CASCADE'),
                    nullable=False, index=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    estimated_cost = Column(Float, nullable=False)
```

- [ ] **Step 2: 建 adaptability.py**

```python
"""ORM 模型 — 任务适配评估结果表

表归属：**Python 写入**。
"""

from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base import Base


class AdaptabilityResultModel(Base):
    __tablename__ = 'adaptability_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    capable = Column(Boolean, nullable=False)
    payload_ok = Column(Boolean, nullable=False)
    battery_ok = Column(Boolean, nullable=False)
    range_ok = Column(Boolean, nullable=False)
    time_ok = Column(Boolean, nullable=False)
    score = Column(Float, nullable=False)
    reasons = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 3: 建 risk_record.py**

```python
"""ORM 模型 — 飞行风险评估记录表

表归属：**Python 写入**。
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base import Base


class RiskRecordModel(Base):
    __tablename__ = 'risk_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    risk_level = Column(String, nullable=False)
    collision_risk = Column(Float, nullable=False)
    weather_risk = Column(Float, nullable=False)
    battery_risk = Column(Float, nullable=False)
    overall_score = Column(Float, nullable=False)
    weather_factor = Column(Float, nullable=True)
    details = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 4: 建 path_plan.py**

```python
"""ORM 模型 — 航线规划结果表

表归属：**Python 写入**。

waypoints 用 JSONB 而非 PostGIS 线几何：领域模型 PathPlan.waypoints
是含到达时间的航点列表，转几何会丢掉时间维度。若将来需要按航线做
空间查询，再补一个由 waypoints 派生的 LINESTRING Z 列。
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base import Base


class PathPlanModel(Base):
    __tablename__ = 'path_plans'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    algorithm = Column(String, nullable=False)
    waypoints = Column(JSONB, nullable=False, default=list)
    total_distance = Column(Float, nullable=False)
    estimated_time = Column(Float, nullable=False)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 5: 验证五张表可导入**

Run: `.venv/Scripts/python.exe -c "from src.db.models.allocation import AllocationRunModel, AllocationItemModel; from src.db.models.adaptability import AdaptabilityResultModel; from src.db.models.risk_record import RiskRecordModel; from src.db.models.path_plan import PathPlanModel; print('ok')"`
Expected: `ok`

- [ ] **Step 6: 提交**

```bash
git add src/db/models/allocation.py src/db/models/adaptability.py src/db/models/risk_record.py src/db/models/path_plan.py
git commit -m "feat(python-db): 新增 5 张算法结果表模型"
```

---

### Task 5: 新增 C 组监控表模型并统一导出

**Files:**
- Create: `src/db/models/monitoring.py`
- Modify: `src/db/models/__init__.py`、`src/db/models/flight_log.py`

**Interfaces:**
- Produces: `FlightSnapshotModel`、`FlightAlertModel`，以及 `src.db.models` 导出全部 10 张表 —— 这一导出是 Task 7 迁移不漏表的前提

- [ ] **Step 1: 建 monitoring.py**

```python
"""ORM 模型 — 飞行监控表（逐点快照 + 告警）

表归属：**Python 写入**。

快照与告警分两张表：两者写入频率（高频追加 vs 低频事件）、查询方式、
保留策略都不同，合表会让快照表被两类语义污染。

ts 用浮点而非时间类型：领域模型 UAVHealthSnapshot.timestamp 是仿真
时间戳（秒），不是墙钟时间；改用 TIMESTAMPTZ 会丢掉仿真语义。
"""

from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry

from src.db.base import Base


class FlightSnapshotModel(Base):
    __tablename__ = 'flight_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    ts = Column(Float, nullable=False)
    position = Column(Geometry('POINT_Z', srid=4326), nullable=False)
    battery_remaining = Column(Float, nullable=False)
    speed = Column(Float, nullable=False)
    heading = Column(Float, nullable=False)
    is_anomaly = Column(Boolean, nullable=False, default=False)
    anomaly_reasons = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FlightAlertModel(Base):
    __tablename__ = 'flight_alerts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    uav_id = Column(String, nullable=False, index=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: 给 flight_log.py 加归属标注**

在文件 docstring 末尾追加一段（其余内容不动）：

```python
"""ORM 模型 — 飞行轨迹表（PostGIS 线几何 + pgvector）

表归属：**Python 写入，但当前暂无写入方**。

它表示「一次飞行会话」的聚合（轨迹线 + 特征向量 + 起止时间 + 总距离），
而现有代码只有逐点快照（flight_snapshots），尚不存在「飞行会话」这一
边界。先把表和列建好，等会话概念落地再接入写入逻辑。
"""
```

- [ ] **Step 3: 改写 models/\_\_init\_\_.py**

```python
"""ORM 模型 — 统一导出

新增模型必须在此导出：alembic/env.py 通过 import src.db.models 触发
全部表注册，漏导出会让 autogenerate 生成 DROP TABLE。
"""

from src.db.models.uav import UAVModel
from src.db.models.task import TaskModel
from src.db.models.flight_log import FlightLogModel
from src.db.models.allocation import AllocationRunModel, AllocationItemModel
from src.db.models.adaptability import AdaptabilityResultModel
from src.db.models.risk_record import RiskRecordModel
from src.db.models.path_plan import PathPlanModel
from src.db.models.monitoring import FlightSnapshotModel, FlightAlertModel

__all__ = [
    "UAVModel",
    "TaskModel",
    "FlightLogModel",
    "AllocationRunModel",
    "AllocationItemModel",
    "AdaptabilityResultModel",
    "RiskRecordModel",
    "PathPlanModel",
    "FlightSnapshotModel",
    "FlightAlertModel",
]
```

- [ ] **Step 4: 验证 10 张表全部注册**

Run: `.venv/Scripts/python.exe -c "import src.db.models as m; from src.db.base import Base; names=sorted(Base.metadata.tables); print(len(names)); print(names)"`
Expected: `10` 与 `['adaptability_results', 'allocation_items', 'allocation_runs', 'flight_alerts', 'flight_logs', 'flight_snapshots', 'path_plans', 'risk_records', 'tasks', 'uavs']`

- [ ] **Step 5: 提交**

```bash
git add src/db/models/monitoring.py src/db/models/flight_log.py src/db/models/__init__.py
git commit -m "feat(python-db): 新增监控表模型并统一导出全部 10 张表"
```

---

### Task 6: Alembic 配置

**Files:**
- Create: `alembic.ini`、`alembic/env.py`、`alembic/script.py.mako`

**Interfaces:**
- Consumes: `get_settings().database_url`（Task 2）、`src.db.models`（Task 5）
- Produces: 可执行 `alembic revision` / `alembic upgrade` 的运行环境 —— Task 7 依赖

- [ ] **Step 1: 生成骨架**

Run: `cd apps/server/python-fastapi-backend && .venv/Scripts/python.exe -m alembic init -t async alembic`
Expected: 生成 `alembic.ini`、`alembic/env.py`、`alembic/script.py.mako`、`alembic/versions/`

- [ ] **Step 2: 改 alembic.ini**

只保留通用配置，URL 留空（由 env.py 注入）。确认 `alembic.ini` 中有：

```ini
[alembic]
script_location = alembic
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
prepend_sys_path = .
sqlalchemy.url =
```

`prepend_sys_path = .` 让 `import src...` 可用。`sqlalchemy.url` 必须留空 —— 避免出现「应用连 A 库、迁移连 B 库」。

- [ ] **Step 3: 改写 env.py**

`alembic/env.py` 全文替换为：

```python
"""Alembic 迁移环境（异步）

URL 来自 src.utils.config.get_settings()，与运行时同源，避免
「应用连 A 库、迁移连 B 库」。
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.db.base import Base
import src.db.models  # noqa: F401  关键：导入全部模型以注册到 Base.metadata
from src.utils.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# get_main_option 会对 % 做插值，DSN 里若有 % 必须转义
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连库"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: 验证 Alembic 能加载模型元数据（不连库）**

Run: `.venv/Scripts/python.exe -m alembic upgrade head --sql > /dev/null && echo ENV_OK`
Expected: `ENV_OK`（离线模式会执行 env.py 但不连库；versions/ 此时为空，正常不输出 SQL）。**不应**出现 `ModuleNotFoundError` 或 `NameError`。若报 `sqlalchemy.url` 相关错误，说明第 2 步的 URL 没留空

> 注意不要用 `alembic heads` 做这个验证 —— 它只读脚本目录，不执行 env.py，验不到导入链。

- [ ] **Step 5: 提交**

```bash
git add alembic.ini alembic/
git commit -m "feat(python-db): 添加 Alembic 异步迁移配置"
```

---

### Task 7: 初始迁移（含扩展与索引）

**Files:**
- Create: `alembic/versions/<rev>_initial_schema.py`

**Interfaces:**
- Consumes: 全部 10 张模型（Task 3~5）、Alembic 配置（Task 6）
- Produces: `st_risk` 库中的 10 张表 —— Task 10~14 依赖

> **前置**：`.env` 的 `UAV_DATABASE_URL` 必须能连上本机 5432，且 `st_risk` 库已存在（`CREATE DATABASE st_risk;`）。未满足时本任务无法执行。

- [ ] **Step 1: 确认前置就绪**

Run: `.venv/Scripts/python.exe -c "import asyncio,asyncpg; from urllib.parse import urlparse; from src.utils.config import get_settings; asyncio.run(asyncpg.connect(get_settings().database_url.replace('postgresql+asyncpg://','postgresql://'), timeout=5))" && echo CONNECT_OK`
Expected: `CONNECT_OK`。失败则先修正 `.env` 与建库，不要继续
注：asyncpg 只认 `postgresql://` 前缀，`+asyncpg` 是给 SQLAlchemy 用的，裸连 asyncpg 前必须去掉（实测 `ClientConfigurationError: invalid DSN`）。

- [ ] **Step 2: 生成迁移骨架**

Run: `.venv/Scripts/python.exe -m alembic revision --autogenerate -m "initial schema"`
Expected: 生成 `alembic/versions/<rev>_initial_schema.py`，`upgrade()` 里含 10 个 `op.create_table`

- [ ] **Step 3: 人工补扩展与向量列导入**

在生成的迁移文件顶部导入区补：

```python
import geoalchemy2
from pgvector.sqlalchemy import Vector
```

在 `upgrade()` 的**最前面**（第一个 `op.create_table` 之前）插入：

```python
    # 几何列与向量列的类型依赖扩展先存在；CREATE EXTENSION 需要超级用户
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

- [ ] **Step 4: 人工核对并补齐索引**

逐条核对生成的 `upgrade()`，确认下列索引存在，缺则补 `op.create_index`：

```python
    # 几何列的 GIST 索引（geoalchemy2 的自动建索引在 autogenerate 下不可靠，逐个核对）
    op.create_index('idx_uavs_position', 'uavs', ['position'], postgresql_using='gist')
    op.create_index('idx_tasks_position', 'tasks', ['position'], postgresql_using='gist')
    op.create_index('idx_flight_snapshots_position', 'flight_snapshots', ['position'],
                    postgresql_using='gist')
    op.create_index('idx_flight_logs_track', 'flight_logs', ['track'], postgresql_using='gist')
    # 向量列的 HNSW 索引
    op.execute("CREATE INDEX idx_flight_logs_embedding ON flight_logs "
               "USING hnsw (embedding vector_l2_ops)")
    # 对比实验常用查询
    op.create_index('idx_allocation_runs_algorithm', 'allocation_runs',
                    ['algorithm', 'created_at'])
    op.create_index('idx_risk_records_uav', 'risk_records', ['uav_id', 'created_at'])
    op.create_index('idx_flight_snapshots_uav', 'flight_snapshots', ['uav_id', 'ts'])
    op.create_index('idx_flight_alerts_uav', 'flight_alerts', ['uav_id', 'created_at'])
```

同时确认 `uavs` / `tasks` 的 `position`、`flight_logs.track` 列类型为 `geoalchemy2.types.Geometry`，`flight_logs.embedding` 为 `Vector(128)`；若 autogenerate 把它们渲染成了别的类型，手工改回。

`downgrade()` 保持只 `op.drop_table`，**不要**加 `DROP EXTENSION` —— 扩展是实例级对象，删除会影响同实例其他库。

- [ ] **Step 5: 执行迁移**

Run: `.venv/Scripts/python.exe -m alembic upgrade head`
Expected: 输出若干 `Running upgrade  -> <rev>, initial schema`，无报错

- [ ] **Step 6: 核对表与列类型**

Run:
```bash
# 从配置读取密码注入 PGPASSWORD（不回显、不落盘、不打印 .env 内容）
export PGPASSWORD=$(.venv/Scripts/python.exe -c "from urllib.parse import urlparse; from src.utils.config import get_settings; print(urlparse(get_settings().database_url).password or '')")
psql -U postgres -h localhost -d st_risk -c "\dt" && \
psql -U postgres -h localhost -d st_risk -c "SELECT f_table_name, f_geometry_column, coord_dimension, srid, type FROM geometry_columns;"
```
Expected: 10 张表；`geometry_columns` 里 `uavs.position`、`tasks.position`、`flight_snapshots.position` 为 `POINTZ`/3/4326，`flight_logs.track` 为 `LINESTRINGZ`/3/4326

- [ ] **Step 7: 验证 downgrade 可回滚**

Run: `.venv/Scripts/python.exe -m alembic downgrade base && .venv/Scripts/python.exe -m alembic upgrade head`
Expected: 两段都无报错（验证迁移可逆）

- [ ] **Step 8: 提交**

```bash
git add alembic/versions/
git commit -m "feat(python-db): 添加初始迁移（10 张表 + 扩展 + 索引）"
```

---

## Phase 3 — 仓储层

### Task 8: 仓储接口改 async 并接通工厂

**Files:**
- Modify: `src/repositories/base.py`、`src/repositories/uav_repo.py`、`src/repositories/flight_log_repo.py`、`src/repositories/adaptability_repo.py`、`src/repositories/risk_repo.py`、`src/services/uav_resource/service.py`、`src/services/flight_monitoring/service.py`、`src/api/v1/endpoints/uav_resource.py`、`src/api/v1/endpoints/flight_monitoring.py`、`src/api/v1/endpoints/task_adaptability.py`
- Modify: `tests/test_services.py`

**Interfaces:**
- Produces: `BaseRepository.save/find_by_id/find_all/delete/exists` 全部为 `async def`；`uav_resource` 与 `flight_monitoring` 的 service 函数全部为 `async def` —— Task 9~12 依赖

**这一整个改动是一个原子单元**：接口改 async 后，内存实现、service、端点、测试必须同时改完，否则测试无法通过。

- [ ] **Step 1: 改 base.py 接口**

`src/repositories/base.py` 中 `BaseRepository` 与 `InMemoryRepository` 的 5 个方法全部加 `async`：

```python
class BaseRepository(Generic[T, ID]):
    """
    通用仓储接口。

    所有具体 Repository 继承此类，实现内存 / 数据库版本。
    """

    async def save(self, entity: T) -> T:
        raise NotImplementedError

    async def find_by_id(self, entity_id: ID) -> T | None:
        raise NotImplementedError

    async def find_all(self) -> list[T]:
        raise NotImplementedError

    async def delete(self, entity_id: ID) -> bool:
        raise NotImplementedError

    async def exists(self, entity_id: ID) -> bool:
        raise NotImplementedError
```

`InMemoryRepository` 的 `save` / `find_by_id` / `find_all` / `delete` / `exists` 同样加 `async`；`count` / `clear` / `_extract_id` 保持同步（它们不是接口方法）。

- [ ] **Step 2: 改四个具体仓储**

`uav_repo.py`、`flight_log_repo.py`、`adaptability_repo.py`、`risk_repo.py` 中所有覆写基类的方法加 `async`，并在函数体内对基类方法的调用加 `await`：

- `uav_repo.py`：`update_status`、`update_position` 内 `self.find_by_id(...)` → `await self.find_by_id(...)`
- `flight_log_repo.py`：方法整体重写为 `async def`（它不继承 `BaseRepository`，五个方法各自加 `async` 即可）
- `adaptability_repo.py` / `risk_repo.py`：`find_by_uav` / `find_by_task` / `find_capable` / `find_high_risk` 加 `async`

> 注：`adaptability_repo.py` 与 `risk_repo.py` 目前**没有任何调用方**（对应的两个评估模块是无状态的）。本次一并对齐为 async 以保持接口一致，但在文件 docstring 里注明「当前无调用方」。

- [ ] **Step 3: 改两个 service 为 async**

`src/services/uav_resource/service.py`：全部函数加 `async`，内部调用加 `await`。`get_uav` 与 `remove_uav` 的异常语义保持不变（仍抛 `InsufficientResourceError`）。

`src/services/flight_monitoring/service.py`：`record_snapshot` / `get_track` / `get_alerts` / `clear_alerts` / `get_active_count` 加 `async`。`detect_anomalies` 保持同步（纯计算）。

- [ ] **Step 4: 端点加 await**

- `src/api/v1/endpoints/uav_resource.py`：所有 `service.xxx(...)` 调用加 `await`
- `src/api/v1/endpoints/flight_monitoring.py`：同上
- `src/api/v1/endpoints/task_adaptability.py`：`uav_resource.get_uav(req.uav_id)` 加 `await`

- [ ] **Step 5: 改造 test_services.py**

`tests/test_services.py` 中六个调用点改为异步：`register_uav` / `get_uav` / `list_uavs` / `update_uav_status` / `record_snapshot` / `get_track`。把涉及它们的测试函数改成 `async def`（`asyncio_mode = "auto"` 会自动接管）：

- 涉及 `uav_resource` 的用例（约 `_make_uav` 相关、`test_get_uav`、`test_list_by_status`）→ `async def` + `await`
- `test_snapshot_record` → `async def` + `await record_snapshot(...)` + `await get_track(...)`
- 只调用 `evaluate` / `evaluate_all` / `assess` 的用例 → **保持同步不动**

- [ ] **Step 6: 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS，数量与改动前一致

- [ ] **Step 7: lint**

Run: `.venv/Scripts/python.exe -m ruff check src/ tests/`
Expected: 无错误

- [ ] **Step 8: 提交**

```bash
git add src/repositories/ src/services/ src/api/ tests/test_services.py
git commit -m "refactor(python-db): 仓储与服务接口改为 async"
```

---

### Task 9: 映射层

**Files:**
- Create: `src/repositories/mappers.py`
- Create: `tests/test_mappers.py`

**Interfaces:**
- Consumes: 领域模型（`src.domain.models`）、ORM 模型（Task 3~5）
- Produces: `position_to_wkt(Position) -> str`、`wkt_to_position(str) -> Position`、`uav_to_model(UAV) -> UAVModel`、`uav_to_domain(UAVModel) -> UAV`、`snapshot_to_model(UAVHealthSnapshot) -> FlightSnapshotModel`、`snapshot_to_domain(FlightSnapshotModel) -> UAVHealthSnapshot`、`risk_to_model(RiskAssessment, weather_factor) -> RiskRecordModel`、`plan_to_model(PathPlan, algorithm, duration_ms) -> PathPlanModel` —— Task 10、12 依赖

> ORM 对象的几何列读出来是 WKBElement，因此 `*_to_domain` 统一用 `from_shape` 解析。为避免在单元测试里依赖数据库，`wkt_to_position` 直接接收 WKT 字符串，测试传入字符串即可。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_mappers.py`：

```python
"""映射层 —— 领域模型 ↔ ORM 模型往返"""

from src.domain.enums import RiskLevel, UAVStatus
from src.domain.models import UAV, Position, RiskAssessment, UAVHealthSnapshot
from src.repositories import mappers


def test_position_wkt_roundtrip_keeps_z():
    """z 分量必须保留 —— POINT_Z 的意义就在这里"""
    pos = Position(x=1.5, y=-2.25, z=30.0)
    assert mappers.wkt_to_position(mappers.position_to_wkt(pos)) == pos


def test_position_wkt_format():
    assert mappers.position_to_wkt(Position(x=1.0, y=2.0, z=3.0)) == "POINT Z (1.0 2.0 3.0)"


def test_uav_to_model_maps_columns():
    uav = UAV(id="uav-1", position=Position(x=1.0, y=2.0, z=3.0),
              speed=10.0, max_payload=5.0, battery=900.0,
              status=UAVStatus.IN_FLIGHT)
    m = mappers.uav_to_model(uav)
    assert m.id == "uav-1"
    assert m.speed == 10.0
    assert m.max_payload == 5.0
    assert m.battery == 900.0
    assert m.status == "in_flight"          # 枚举落库为字符串值
    assert "POINT Z (1.0 2.0 3.0)" in str(m.position)


def test_uav_status_enum_maps_to_value_not_name():
    """落库必须是 'in_flight' 而不是 'IN_FLIGHT'"""
    uav = UAV(id="u", position=Position(x=0, y=0, z=0), speed=1.0,
              max_payload=1.0, battery=1.0, status=UAVStatus.RETURNING)
    assert mappers.uav_to_model(uav).status == "returning"


def test_snapshot_to_model_keeps_reasons_list():
    snap = UAVHealthSnapshot(uav_id="uav-1", position=Position(x=0, y=0, z=50),
                             battery_remaining=8.0, speed=31.0, heading=90.0,
                             timestamp=12.5, is_anomaly=True,
                             anomaly_reasons=["电量过低", "速度异常"])
    m = mappers.snapshot_to_model(snap)
    assert m.uav_id == "uav-1"
    assert m.ts == 12.5
    assert m.is_anomaly is True
    assert m.anomaly_reasons == ["电量过低", "速度异常"]


def test_risk_to_model_flattens_fields():
    assessment = RiskAssessment(uav_id="uav-1", task_id="task-1",
                                risk_level=RiskLevel.HIGH,
                                collision_risk=0.8, weather_risk=0.2,
                                battery_risk=0.3, overall_score=0.6,
                                details=["碰撞风险偏高"])
    m = mappers.risk_to_model(assessment, weather_factor=0.4)
    assert m.risk_level == "high"
    assert m.overall_score == 0.6
    assert m.weather_factor == 0.4
    assert m.details == ["碰撞风险偏高"]
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_mappers.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'src.repositories.mappers'`

- [ ] **Step 3: 实现 mappers.py**

```python
"""领域模型 ↔ ORM 模型映射

没有这一层，ORM 对象会一路漏进 service 与响应模型。集中在此，
service 只需面对领域模型。

几何列统一用 WKT 文本在 Python 侧进出：读写都用 ST_GeomFromText /
ST_AsText，避免在业务代码里处理 WKBElement。
"""

from src.db.models.adaptability import AdaptabilityResultModel
from src.db.models.monitoring import FlightSnapshotModel
from src.db.models.path_plan import PathPlanModel
from src.db.models.risk_record import RiskRecordModel
from src.db.models.uav import UAVModel
from src.domain.enums import UAVStatus
from src.domain.models import (
    UAV,
    AdaptabilityResult,
    PathPlan,
    Position,
    RiskAssessment,
    UAVHealthSnapshot,
)


# ── 几何 ─────────────────────────────────────────────

def position_to_wkt(pos: Position) -> str:
    """Position -> PostGIS 可解析的 WKT 文本（含 z）"""
    return f"POINT Z ({pos.x} {pos.y} {pos.z})"


def wkt_to_position(wkt: str) -> Position:
    """WKT 文本 -> Position

    支持 'POINT Z (x y z)' 与 'POINT(x y z)' 两种写法。
    """
    body = wkt[wkt.index("(") + 1: wkt.index(")")].replace(",", " ")
    parts = [float(v) for v in body.split()]
    return Position(x=parts[0], y=parts[1], z=parts[2] if len(parts) > 2 else 0.0)


# ── ① 无人机 ──────────────────────────────────────────

def uav_to_model(uav: UAV) -> UAVModel:
    return UAVModel(
        id=uav.id,
        position=position_to_wkt(uav.position),
        speed=uav.speed,
        max_payload=uav.max_payload,
        battery=uav.battery,
        status=uav.status.value,
    )


def uav_to_domain(row) -> UAV:
    """row 需提供 id / position_wkt(WKT 文本) / speed / max_payload / battery / status

    position 列由查询里的 ST_AsText(...) 别名 position_wkt 提供 ——
    不能直接读 row.position，那是 WKBElement 而非文本。
    """
    return UAV(
        id=row.id,
        position=wkt_to_position(row.position_wkt),
        speed=row.speed,
        max_payload=row.max_payload,
        battery=row.battery,
        status=UAVStatus(row.status),
    )


# ── ⑥ 监控快照 ────────────────────────────────────────

def snapshot_to_model(snap: UAVHealthSnapshot) -> FlightSnapshotModel:
    return FlightSnapshotModel(
        uav_id=snap.uav_id,
        ts=snap.timestamp,
        position=position_to_wkt(snap.position),
        battery_remaining=snap.battery_remaining,
        speed=snap.speed,
        heading=snap.heading,
        is_anomaly=snap.is_anomaly,
        anomaly_reasons=list(snap.anomaly_reasons),
    )


def snapshot_to_domain(row) -> UAVHealthSnapshot:
    """row 需提供 uav_id / ts / battery_remaining / speed / heading /
    is_anomaly / anomaly_reasons / position_wkt(WKT 文本)"""
    return UAVHealthSnapshot(
        uav_id=row.uav_id,
        position=wkt_to_position(row.position_wkt),
        battery_remaining=row.battery_remaining,
        speed=row.speed,
        heading=row.heading,
        timestamp=row.ts,
        is_anomaly=row.is_anomaly,
        anomaly_reasons=list(row.anomaly_reasons or []),
    )


# ── ③ 风险评估 ────────────────────────────────────────

def risk_to_model(assessment: RiskAssessment, weather_factor: float | None = None) -> RiskRecordModel:
    return RiskRecordModel(
        uav_id=assessment.uav_id,
        task_id=assessment.task_id,
        risk_level=assessment.risk_level.value,
        collision_risk=assessment.collision_risk,
        weather_risk=assessment.weather_risk,
        battery_risk=assessment.battery_risk,
        overall_score=assessment.overall_score,
        weather_factor=weather_factor,
        details=list(assessment.details),
    )


# ── ② 适配评估 ────────────────────────────────────────

def adaptability_to_model(result: AdaptabilityResult) -> AdaptabilityResultModel:
    return AdaptabilityResultModel(
        uav_id=result.uav_id,
        task_id=result.task_id,
        capable=result.capable,
        payload_ok=result.payload_ok,
        battery_ok=result.battery_ok,
        range_ok=result.range_ok,
        time_ok=result.time_ok,
        score=result.score,
        reasons=list(result.reasons),
    )


# ── ⑤ 航线规划 ────────────────────────────────────────

def plan_to_model(plan: PathPlan, algorithm: str, duration_ms: float | None = None) -> PathPlanModel:
    return PathPlanModel(
        uav_id=plan.uav_id,
        task_id=plan.task_id,
        algorithm=algorithm,
        waypoints=[{"x": w.position.x, "y": w.position.y, "z": w.position.z,
                    "arrival_time": w.arrival_time} for w in plan.waypoints],
        total_distance=plan.total_distance,
        estimated_time=plan.estimated_time,
        duration_ms=duration_ms,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_mappers.py -q`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add src/repositories/mappers.py tests/test_mappers.py
git commit -m "feat(python-db): 添加领域模型与 ORM 模型映射层"
```

---

### Task 10: SQLAlchemy 仓储实现

**Files:**
- Create: `src/repositories/db/__init__.py`、`src/repositories/db/uav_repo.py`、`src/repositories/db/monitoring_repo.py`、`src/repositories/db/allocation_repo.py`、`src/repositories/db/record_repo.py`
- Create: `tests/test_db_persistence.py`

**Interfaces:**
- Consumes: `mappers`（Task 9）、模型（Task 3~5）
- Produces: `UAVDbRepository(session_factory)`、`FlightLogDbRepository(session_factory)`、`AllocationRunDbRepository(session_factory)`、`AdaptabilityDbRepository(session_factory)`、`RiskRecordDbRepository(session_factory)`、`PathPlanDbRepository(session_factory)` —— Task 11 工厂依赖

**设计：** 每个方法 `async with self._session_factory() as session` 开一个短会话并提交，事务边界即方法边界。这样 session 不渗透到 service 签名。

> **前置**：需要 Task 7 的迁移已执行。这些测试打 `@pytest.mark.integration`，默认被 `addopts` 跳过。

- [ ] **Step 1: 建 db/__init__.py**

```python
"""基于 SQLAlchemy 的仓储实现 —— 每个方法一个短会话"""

from src.repositories.db.allocation_repo import AllocationRunDbRepository
from src.repositories.db.monitoring_repo import FlightLogDbRepository
from src.repositories.db.record_repo import (AdaptabilityDbRepository,
                                             PathPlanDbRepository,
                                             RiskRecordDbRepository)
from src.repositories.db.uav_repo import UAVDbRepository

__all__ = [
    "UAVDbRepository",
    "FlightLogDbRepository",
    "AllocationRunDbRepository",
    "AdaptabilityDbRepository",
    "RiskRecordDbRepository",
    "PathPlanDbRepository",
]
```

- [ ] **Step 2: 建 uav_repo.py**

```python
"""① 无人机仓储 — PostgreSQL 实现"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.uav import UAVModel
from src.domain.enums import UAVStatus
from src.domain.models import Position, UAV
from src.repositories import mappers


class UAVDbRepository:
    """无人机仓储 —— 表归属标注见 src/db/models/uav.py（将来写权限归 Node）"""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _select():
        """逐列显式选取 + ST_AsText 别名。

        必须显式列：select(Model, label) 的结果行只能按 "Model"/"label"
        两个键取属性，row.id / row.position_wkt 会 AttributeError。
        显式列后行对象按列名暴露属性，mappers.uav_to_domain(row) 可直接用。
        """
        return select(
            UAVModel.id,
            UAVModel.speed,
            UAVModel.max_payload,
            UAVModel.battery,
            UAVModel.status,
            func.ST_AsText(UAVModel.position).label("position_wkt"),
        )

    async def save(self, uav: UAV) -> UAV:
        async with self._session_factory() as session:
            model = mappers.uav_to_model(uav)
            await session.merge(model)
            await session.commit()
        return uav

    async def find_by_id(self, uav_id: str) -> UAV | None:
        async with self._session_factory() as session:
            row = (await session.execute(
                self._select().where(UAVModel.id == uav_id))).first()
        return mappers.uav_to_domain(row) if row else None

    async def find_all(self) -> list[UAV]:
        async with self._session_factory() as session:
            rows = (await session.execute(self._select().order_by(UAVModel.id))).all()
        return [mappers.uav_to_domain(r) for r in rows]

    async def find_by_status(self, status: UAVStatus) -> list[UAV]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                self._select().where(UAVModel.status == status.value)
                .order_by(UAVModel.id))).all()
        return [mappers.uav_to_domain(r) for r in rows]

    async def delete(self, uav_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(delete(UAVModel).where(UAVModel.id == uav_id))
            await session.commit()
        return result.rowcount > 0

    async def exists(self, uav_id: str) -> bool:
        return await self.find_by_id(uav_id) is not None

    async def update_status(self, uav_id: str, status: UAVStatus) -> UAV | None:
        async with self._session_factory() as session:
            model = await session.get(UAVModel, uav_id)
            if model is None:
                return None
            model.status = status.value
            await session.commit()
        return await self.find_by_id(uav_id)

    async def update_position(self, uav_id: str, x: float, y: float, z: float) -> UAV | None:
        async with self._session_factory() as session:
            model = await session.get(UAVModel, uav_id)
            if model is None:
                return None
            model.position = mappers.position_to_wkt(Position(x=x, y=y, z=z))
            await session.commit()
        return await self.find_by_id(uav_id)
```

- [ ] **Step 3: 建 monitoring_repo.py**

```python
"""⑥ 飞行监控仓储 — PostgreSQL 实现（快照 + 告警）"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.monitoring import FlightAlertModel, FlightSnapshotModel
from src.domain.models import UAVHealthSnapshot
from src.repositories import mappers


class FlightLogDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    # ── 快照 ──

    async def append_snapshot(self, snapshot: UAVHealthSnapshot) -> None:
        async with self._session_factory() as session:
            session.add(mappers.snapshot_to_model(snapshot))
            await session.commit()

    async def get_track(self, uav_id: str, limit: int = 100) -> list[UAVHealthSnapshot]:
        async with self._session_factory() as session:
            subq = (select(FlightSnapshotModel.id)
                    .where(FlightSnapshotModel.uav_id == uav_id)
                    .order_by(FlightSnapshotModel.ts.desc(), FlightSnapshotModel.id.desc())
                    .limit(limit).subquery())
            # 逐列显式选取：行对象按列名暴露属性，snapshot_to_domain 直接消费
            rows = (await session.execute(
                select(
                    FlightSnapshotModel.uav_id,
                    FlightSnapshotModel.ts,
                    FlightSnapshotModel.battery_remaining,
                    FlightSnapshotModel.speed,
                    FlightSnapshotModel.heading,
                    FlightSnapshotModel.is_anomaly,
                    FlightSnapshotModel.anomaly_reasons,
                    func.ST_AsText(FlightSnapshotModel.position).label("position_wkt"),
                )
                .where(FlightSnapshotModel.id.in_(select(subq.c.id)))
                .order_by(FlightSnapshotModel.ts.asc(), FlightSnapshotModel.id.asc())
            )).all()
        return [mappers.snapshot_to_domain(r) for r in rows]

    async def get_latest(self, uav_id: str) -> UAVHealthSnapshot | None:
        track = await self.get_track(uav_id, limit=1)
        return track[-1] if track else None

    async def get_active_uav_ids(self) -> list[str]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(FlightSnapshotModel.uav_id).distinct()
                .order_by(FlightSnapshotModel.uav_id))).all()
        return [r.uav_id for r in rows]

    # ── 告警 ──

    async def append_alert(self, uav_id: str, alert: str) -> None:
        async with self._session_factory() as session:
            session.add(FlightAlertModel(uav_id=uav_id, message=alert))
            await session.commit()

    async def get_alerts(self, uav_id: str) -> list[str]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(FlightAlertModel.message)
                .where(FlightAlertModel.uav_id == uav_id)
                .order_by(FlightAlertModel.id))).all()
        return [r.message for r in rows]

    async def clear_alerts(self, uav_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(FlightAlertModel).where(FlightAlertModel.uav_id == uav_id))
            await session.commit()
```

- [ ] **Step 4: 建 allocation_repo.py**

```python
"""④ 任务分配结果仓储 — PostgreSQL 实现（run + 明细）"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.allocation import AllocationItemModel, AllocationRunModel
from src.domain.models import TaskAllocation


class AllocationRunDbRepository:
    """一次分配调用 = 一条 run + N 条 item"""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_run(
        self,
        *,
        algorithm: str,
        params: dict | None,
        uav_count: int,
        task_count: int,
        allocations: list[TaskAllocation],
        unassigned_task_ids: list[str],
        duration_ms: float | None = None,
    ) -> uuid.UUID:
        async with self._session_factory() as session:
            run = AllocationRunModel(
                algorithm=algorithm,
                params=params,
                uav_count=uav_count,
                task_count=task_count,
                assigned_count=len(allocations),
                unassigned_count=len(unassigned_task_ids),
                unassigned_task_ids=list(unassigned_task_ids),
                duration_ms=duration_ms,
            )
            session.add(run)
            await session.flush()          # 取得 run.id
            run_id = run.id
            session.add_all([
                AllocationItemModel(run_id=run_id, uav_id=a.uav_id,
                                    task_id=a.task_id, estimated_cost=a.estimated_cost)
                for a in allocations
            ])
            await session.commit()
        return run_id

    async def list_runs(self, algorithm: str | None = None, limit: int = 50) -> list[dict]:
        """返回 run 摘要（不含明细）"""
        async with self._session_factory() as session:
            stmt = select(AllocationRunModel).order_by(AllocationRunModel.created_at.desc()).limit(limit)
            if algorithm:
                stmt = stmt.where(AllocationRunModel.algorithm == algorithm)
            rows = (await session.execute(stmt)).scalars().all()
        return [self._summary(r) for r in rows]

    async def count_runs(self, algorithm: str | None = None) -> int:
        """匹配条件的 run 总数（不受 limit 影响，供分页 total 使用）"""
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(AllocationRunModel)
            if algorithm:
                stmt = stmt.where(AllocationRunModel.algorithm == algorithm)
            return (await session.execute(stmt)).scalar_one()

    async def get_run(self, run_id: uuid.UUID) -> dict | None:
        """返回 run 摘要 + 明细"""
        async with self._session_factory() as session:
            run = await session.get(AllocationRunModel, run_id)
            if run is None:
                return None
            items = (await session.execute(
                select(AllocationItemModel).where(AllocationItemModel.run_id == run_id)
                .order_by(AllocationItemModel.id))).scalars().all()
        data = self._summary(run)
        data["allocations"] = [
            TaskAllocation(uav_id=i.uav_id, task_id=i.task_id, estimated_cost=i.estimated_cost)
            for i in items
        ]
        return data

    @staticmethod
    def _summary(run: AllocationRunModel) -> dict:
        return {
            "id": run.id,
            "algorithm": run.algorithm,
            "params": run.params,
            "uav_count": run.uav_count,
            "task_count": run.task_count,
            "assigned_count": run.assigned_count,
            "unassigned_count": run.unassigned_count,
            "unassigned_task_ids": list(run.unassigned_task_ids or []),
            "duration_ms": run.duration_ms,
            "created_at": run.created_at,
        }
```

- [ ] **Step 5: 建 record_repo.py**

三个结构相同的扁平记录仓储，每个只做「存一批」+「按 uav/task 查」：

```python
"""②③⑤ 扁平结果记录仓储 — PostgreSQL 实现

适配评估、风险评估、航线规划都是「一次调用产生若干条独立记录」，
没有 run 概念，因此各自一张表、各自一个仓储。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.adaptability import AdaptabilityResultModel
from src.db.models.path_plan import PathPlanModel
from src.db.models.risk_record import RiskRecordModel
from src.domain.models import AdaptabilityResult, PathPlan, RiskAssessment
from src.repositories import mappers


class AdaptabilityDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_many(self, results: list[AdaptabilityResult]) -> None:
        if not results:
            return
        async with self._session_factory() as session:
            session.add_all([mappers.adaptability_to_model(r) for r in results])
            await session.commit()

    async def find_by_uav(self, uav_id: str, limit: int = 100) -> list[dict]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(AdaptabilityResultModel)
                .where(AdaptabilityResultModel.uav_id == uav_id)
                .order_by(AdaptabilityResultModel.created_at.desc()).limit(limit))
            ).scalars().all()
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: AdaptabilityResultModel) -> dict:
        return {
            "id": r.id, "uav_id": r.uav_id, "task_id": r.task_id,
            "capable": r.capable, "payload_ok": r.payload_ok, "battery_ok": r.battery_ok,
            "range_ok": r.range_ok, "time_ok": r.time_ok, "score": r.score,
            "reasons": list(r.reasons or []), "created_at": r.created_at,
        }


class RiskRecordDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(self, assessment: RiskAssessment, weather_factor: float | None = None) -> None:
        async with self._session_factory() as session:
            session.add(mappers.risk_to_model(assessment, weather_factor))
            await session.commit()

    async def find_by_uav(self, uav_id: str, limit: int = 100) -> list[dict]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(RiskRecordModel).where(RiskRecordModel.uav_id == uav_id)
                .order_by(RiskRecordModel.created_at.desc()).limit(limit))
            ).scalars().all()
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: RiskRecordModel) -> dict:
        return {
            "id": r.id, "uav_id": r.uav_id, "task_id": r.task_id,
            "risk_level": r.risk_level, "collision_risk": r.collision_risk,
            "weather_risk": r.weather_risk, "battery_risk": r.battery_risk,
            "overall_score": r.overall_score, "weather_factor": r.weather_factor,
            "details": list(r.details or []), "created_at": r.created_at,
        }


class PathPlanDbRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(self, plan: PathPlan, algorithm: str,
                   duration_ms: float | None = None) -> None:
        async with self._session_factory() as session:
            session.add(mappers.plan_to_model(plan, algorithm, duration_ms))
            await session.commit()

    async def find_by_uav(self, uav_id: str, limit: int = 100) -> list[dict]:
        async with self._session_factory() as session:
            rows = (await session.execute(
                select(PathPlanModel).where(PathPlanModel.uav_id == uav_id)
                .order_by(PathPlanModel.created_at.desc()).limit(limit))
            ).scalars().all()
        return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: PathPlanModel) -> dict:
        return {
            "id": r.id, "uav_id": r.uav_id, "task_id": r.task_id,
            "algorithm": r.algorithm, "waypoints": list(r.waypoints or []),
            "total_distance": r.total_distance, "estimated_time": r.estimated_time,
            "duration_ms": r.duration_ms, "created_at": r.created_at,
        }
```

- [ ] **Step 6: 写集成测试**

新建 `tests/test_db_persistence.py`：

```python
"""持久化集成测试 —— 需要真实 PostgreSQL（PostGIS + pgvector）

默认被 pyproject 的 addopts 跳过。显式运行：
    pytest tests/test_db_persistence.py -q -m integration
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import UAVModel
from src.domain.enums import RiskLevel, UAVStatus
from src.domain.models import Position, RiskAssessment, TaskAllocation, UAV
from src.repositories.db import (AdaptabilityDbRepository, AllocationRunDbRepository,
                                 FlightLogDbRepository, RiskRecordDbRepository,
                                 UAVDbRepository)
from src.utils.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
async def session_factory():
    engine = create_async_engine(get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def clean_uavs(session_factory):
    """用例前后各清一次 uavs 表，避免相互污染"""
    from sqlalchemy import delete
    async with session_factory() as s:
        await s.execute(delete(UAVModel))
        await s.commit()
    yield
    async with session_factory() as s:
        await s.execute(delete(UAVModel))
        await s.commit()


async def test_uav_roundtrip_keeps_z(session_factory, clean_uavs):
    """PostGIS POINT_Z 往返后 z 分量不能丢"""
    repo = UAVDbRepository(session_factory)
    uav = UAV(id="uav-z", position=Position(x=1.0, y=2.0, z=42.0),
              speed=10.0, max_payload=5.0, battery=900.0,
              status=UAVStatus.IN_FLIGHT)
    await repo.save(uav)

    got = await repo.find_by_id("uav-z")
    assert got is not None
    assert got.position.z == 42.0
    assert got.position.x == 1.0
    assert got.status == UAVStatus.IN_FLIGHT


async def test_uav_find_by_status_and_delete(session_factory, clean_uavs):
    repo = UAVDbRepository(session_factory)
    await repo.save(UAV(id="u1", position=Position(x=0, y=0, z=0), speed=1.0,
                        max_payload=1.0, battery=10.0, status=UAVStatus.IDLE))
    await repo.save(UAV(id="u2", position=Position(x=0, y=0, z=0), speed=1.0,
                        max_payload=1.0, battery=10.0, status=UAVStatus.MAINTENANCE))

    assert [u.id for u in await repo.find_by_status(UAVStatus.MAINTENANCE)] == ["u2"]
    assert await repo.delete("u1") is True
    assert await repo.find_by_id("u1") is None


async def test_allocation_run_saves_items_matching_assigned_count(session_factory):
    """assigned_count 必须与实际写入的 items 行数一致"""
    repo = AllocationRunDbRepository(session_factory)
    run_id = await repo.save_run(
        algorithm="hungarian",
        params={"foo": 1},
        uav_count=2,
        task_count=3,
        allocations=[TaskAllocation(uav_id="u1", task_id="t1", estimated_cost=1.5),
                     TaskAllocation(uav_id="u2", task_id="t2", estimated_cost=2.5)],
        unassigned_task_ids=["t3"],
        duration_ms=12.0,
    )

    detail = await repo.get_run(run_id)
    assert detail is not None
    assert detail["assigned_count"] == 2
    assert len(detail["allocations"]) == 2
    assert detail["unassigned_task_ids"] == ["t3"]
    assert detail["params"] == {"foo": 1}


async def test_allocation_run_not_found_returns_none(session_factory):
    repo = AllocationRunDbRepository(session_factory)
    assert await repo.get_run(uuid.uuid4()) is None


async def test_risk_record_roundtrip_keeps_details(session_factory):
    repo = RiskRecordDbRepository(session_factory)
    assessment = RiskAssessment(uav_id="u-risk", task_id="t-risk",
                                risk_level=RiskLevel.CRITICAL,
                                collision_risk=0.9, weather_risk=0.8,
                                battery_risk=0.2, overall_score=0.85,
                                details=["高风险"])
    await repo.save(assessment, weather_factor=0.7)

    rows = await repo.find_by_uav("u-risk")
    assert len(rows) >= 1
    assert rows[0]["risk_level"] == "critical"
    assert rows[0]["details"] == ["高风险"]
    assert rows[0]["weather_factor"] == 0.7


async def test_adaptability_save_many_empty_is_noop(session_factory):
    repo = AdaptabilityDbRepository(session_factory)
    await repo.save_many([])   # 不应抛异常


async def test_snapshot_track_roundtrip(session_factory):
    from src.domain.models import UAVHealthSnapshot
    repo = FlightLogDbRepository(session_factory)
    await repo.append_snapshot(UAVHealthSnapshot(
        uav_id="u-mon", position=Position(x=1.0, y=1.0, z=55.0),
        battery_remaining=44.0, speed=12.0, heading=180.0, timestamp=1000.0))
    await repo.append_alert("u-mon", "电量过低: 8.0Wh")

    track = await repo.get_track("u-mon")
    assert any(s.position.z == 55.0 for s in track)
    assert "电量过低: 8.0Wh" in await repo.get_alerts("u-mon")
    await repo.clear_alerts("u-mon")
    assert await repo.get_alerts("u-mon") == []
```

- [ ] **Step 7: 确认默认被跳过**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS，输出含 `deselected`（集成测试被跳过）

- [ ] **Step 8: 连真库跑集成测试**

Run: `.venv/Scripts/python.exe -m pytest tests/test_db_persistence.py -q -m integration`
Expected: 全部 PASS。失败时先看报错是几何 WKT 取列问题还是事务问题，按 Step 2 的「实现提示」调整 `_select()`

- [ ] **Step 9: 提交**

```bash
git add src/repositories/db/ tests/test_db_persistence.py
git commit -m "feat(python-db): 添加 SQLAlchemy 仓储实现与集成测试"
```

---

### Task 11: 仓储工厂与配置切换

**Files:**
- Create: `src/repositories/factory.py`
- Modify: `src/services/uav_resource/service.py`、`src/services/flight_monitoring/service.py`

**Interfaces:**
- Consumes: `get_settings()`（Task 2）、DB 仓储（Task 10）、内存仓储（Task 8）
- Produces: `get_uav_repository()`、`get_flight_log_repository()`、`get_result_repository(name: str)` —— Task 12 依赖

- [ ] **Step 1: 写失败测试**

新建 `tests/test_repository_factory.py`：

```python
"""仓储工厂 —— 默认必须是内存实现"""

import pytest

from src.repositories import factory
from src.repositories.flight_log_repo import FlightLogRepository
from src.repositories.uav_repo import UAVRepository


@pytest.fixture(autouse=True)
def _clear_repo_caches():
    """本文件会往工厂的 lru_cache 写入 db 后端结果；同一 pytest 进程里的
    test_services.py 等也调用同一批工厂函数，不清缓存会把 db 实现泄漏过去
    （无库环境直接连库失败）。"""
    factory.get_uav_repository.cache_clear()
    factory.get_flight_log_repository.cache_clear()
    yield
    factory.get_uav_repository.cache_clear()
    factory.get_flight_log_repository.cache_clear()


def test_default_backend_is_memory():
    """无库环境下服务必须能起 —— 默认返回内存实现"""
    assert isinstance(factory.get_uav_repository(), UAVRepository)
    assert isinstance(factory.get_flight_log_repository(), FlightLogRepository)


def test_db_backend_returns_sqlalchemy_repository(monkeypatch):
    monkeypatch.setattr(factory.get_settings(), "repository_backend", "db", raising=False)
    # 上一个用例已把 memory 结果写进 lru_cache，不清缓存本用例会拿到旧结果
    factory.get_uav_repository.cache_clear()
    repo = factory.get_uav_repository()
    assert repo.__class__.__name__ == "UAVDbRepository"


def test_unknown_backend_raises_value_error():
    import pytest
    with pytest.raises(ValueError, match="repository_backend"):
        factory._build_uav_repo("bogus")
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repository_factory.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'src.repositories.factory'`

- [ ] **Step 3: 实现 factory.py**

```python
"""仓储工厂 —— 按 UAV_REPOSITORY_BACKEND 返回内存或数据库实现

默认 memory：保证无库环境下服务可启动、测试可跑。
本地验真库时设 UAV_REPOSITORY_BACKEND=db。
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.repositories.flight_log_repo import FlightLogRepository
from src.repositories.uav_repo import UAVRepository
from src.utils.config import get_settings


@lru_cache
def _session_factory() -> async_sessionmaker:
    """复用全局引擎的 sessionmaker，避免每次调用新建连接池"""
    from src.db.engine import AsyncSessionLocal
    return AsyncSessionLocal


def _build_uav_repo(backend: str):
    if backend == "memory":
        return UAVRepository()
    if backend == "db":
        from src.repositories.db import UAVDbRepository
        return UAVDbRepository(_session_factory())
    raise ValueError(f"未知的 repository_backend: {backend!r}（应为 'memory' 或 'db'）")


def _build_flight_log_repo(backend: str):
    if backend == "memory":
        return FlightLogRepository()
    if backend == "db":
        from src.repositories.db import FlightLogDbRepository
        return FlightLogDbRepository(_session_factory())
    raise ValueError(f"未知的 repository_backend: {backend!r}（应为 'memory' 或 'db'）")


@lru_cache
def get_uav_repository():
    return _build_uav_repo(get_settings().repository_backend)


@lru_cache
def get_flight_log_repository():
    return _build_flight_log_repo(get_settings().repository_backend)


def get_result_repository(name: str):
    """name ∈ {'allocation', 'adaptability', 'risk', 'path_plan'}

    结果表只在 db 模式下有实现；memory 模式下返回 None，
    调用方据此跳过落库（与 UAV_PERSIST_RESULTS=off 等价）。
    """
    if get_settings().repository_backend != "db":
        return None
    from src.repositories.db import (AdaptabilityDbRepository,
                                     AllocationRunDbRepository,
                                     PathPlanDbRepository,
                                     RiskRecordDbRepository)
    mapping = {
        "allocation": AllocationRunDbRepository,
        "adaptability": AdaptabilityDbRepository,
        "risk": RiskRecordDbRepository,
        "path_plan": PathPlanDbRepository,
    }
    if name not in mapping:
        raise ValueError(f"未知的结果仓储: {name!r}，可选 {sorted(mapping)}")
    return mapping[name](_session_factory())
```

- [ ] **Step 4: service 改走工厂**

`src/services/uav_resource/service.py` 与 `src/services/flight_monitoring/service.py` 中把模块级单例

```python
_repo = UAVRepository()
```

改为函数式获取：

```python
def get_repository():
    return factory.get_uav_repository()
```

并把原有的 `_repo.xxx(...)` 调用换成 `get_repository().xxx(...)`。

> 不要还原成模块级 `_repo = factory.get_uav_repository()` —— 那会在导入时固化后端选择，`monkeypatch` 测试与配置热切换都会失效。

- [ ] **Step 5: 密闭 test_config 的默认值测试**

Task 2 的两个默认值测试直接调 `Settings()`，会读真实环境变量与 `.env` 文件。本任务起，真库验证时 `.env` 里会设 `UAV_REPOSITORY_BACKEND=db`（根 `.env` 现有 8 个 `UAV_` 键），这两个测试会误失败。把它们改为密闭的：

```python
def test_repository_backend_defaults_to_memory(monkeypatch):
    """默认必须是内存实现 —— 无库环境下服务要能起来"""
    monkeypatch.delenv("UAV_REPOSITORY_BACKEND", raising=False)
    assert Settings(_env_file=None).repository_backend == "memory"


def test_persist_results_defaults_to_true(monkeypatch):
    monkeypatch.delenv("UAV_PERSIST_RESULTS", raising=False)
    assert Settings(_env_file=None).persist_results is True
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: 4 passed

- [ ] **Step 6: 运行确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repository_factory.py tests/test_services.py tests/test_config.py -q`
Expected: 全部 PASS

- [ ] **Step 7: 全量回归**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS

- [ ] **Step 8: 提交**

```bash
git add src/repositories/factory.py src/services/ tests/test_repository_factory.py tests/test_config.py
git commit -m "feat(python-db): 添加仓储工厂并支持按配置切换内存/数据库"
```

---

## Phase 4 — 服务与端点

### Task 12: 算法结果落库

**Files:**
- Modify: `src/api/v1/endpoints/task_allocation.py`、`risk_assessment.py`、`route_planning.py`、`task_adaptability.py`

**Interfaces:**
- Consumes: `get_result_repository(name)`（Task 11）、`get_settings().persist_results`（Task 2）
- Produces: 四个算法端点写入对应结果表 —— Task 13 读端点依赖 `allocation_runs`

**约定：** 落库放在 endpoint 层（编排层），service 保持纯函数。`duration_ms` 由端点计时。**写库失败让请求返回 500**（不吞异常）—— 静默丢实验数据比报错危险。

- [ ] **Step 1: 建落库辅助**

新建 `src/api/v1/endpoints/_persist.py`：

```python
"""结果落库辅助 —— 统一处理「未启用持久化」的分支

持久化在两种情况下跳过：
  1. UAV_REPOSITORY_BACKEND != 'db'（无库，走内存）
  2. UAV_PERSIST_RESULTS=off（显式关闭）

两种情况都返回 None，调用方直接忽略返回值。写库异常不在此捕获 ——
让它冒泡成 500，避免静默丢失实验数据。
"""

from src.repositories import factory
from src.utils.config import get_settings


def result_repo(name: str):
    if not get_settings().persist_results:
        return None
    return factory.get_result_repository(name)
```

- [ ] **Step 2: 任务分配端点落库**

`src/api/v1/endpoints/task_allocation.py` 的 `allocate_tasks` 改为：

```python
import time

from src.api.v1.endpoints._persist import result_repo

@router.post("/allocate", response_model=AllocateResponse)
async def allocate_tasks(req: AllocateRequest) -> AllocateResponse:
    """提交任务分配请求"""
    started = time.perf_counter()
    try:
        allocations, unassigned = service.allocate(
            uavs=req.uavs,
            tasks=req.tasks,
            algorithm=req.algorithm,
            params=req.params,
        )
    # 算法不存在、算法参数非法 — 均为客户端错误，须回传 400 而非 500
    except (AlgorithmNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo = result_repo("allocation")
    if repo is not None:
        await repo.save_run(
            algorithm=req.algorithm,
            params=req.params,
            uav_count=len(req.uavs),
            task_count=len(req.tasks),
            allocations=allocations,
            unassigned_task_ids=unassigned,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    return AllocateResponse(
        allocations=allocations,
        unassigned_tasks=unassigned,
        algorithm_used=req.algorithm,
    )
```

- [ ] **Step 3: 风险评估端点落库**

`src/api/v1/endpoints/risk_assessment.py` 的 `assess_risk`：在算出 `assessment` 之后、构造响应之前插入：

```python
    repo = result_repo("risk")
    if repo is not None:
        await repo.save(assessment, weather_factor=req.weather_factor)
```

- [ ] **Step 4: 航线规划端点落库**

`src/api/v1/endpoints/route_planning.py` 的 `plan_path`：加 `started = time.perf_counter()` 于函数首行，并在 `return PlanResponse(...)` 之前插入：

```python
    repo = result_repo("path_plan")
    if repo is not None:
        await repo.save(plan, algorithm=req.algorithm,
                        duration_ms=(time.perf_counter() - started) * 1000)
```

- [ ] **Step 5: 适配评估端点落库**

`src/api/v1/endpoints/task_adaptability.py` 的两个端点各插一段：

```python
    repo = result_repo("adaptability")
    if repo is not None:
        await repo.save_many([result])
```

`/batch` 端点用 `await repo.save_many(results)`（一次写入全部）。

- [ ] **Step 6: 确认默认路径不受影响**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS（默认 memory 模式，`result_repo` 返回 None，落库整段被跳过）—— 这一步验证「无库时端点行为不变」

- [ ] **Step 7: lint**

Run: `.venv/Scripts/python.exe -m ruff check src/`
Expected: 无错误

- [ ] **Step 8: 提交**

```bash
git add src/api/v1/endpoints/
git commit -m "feat(python-db): 四个算法端点写入结果表"
```

---

### Task 13: 任务分配读端点

**Files:**
- Modify: `src/schemas/task_allocation.py`、`src/api/v1/endpoints/task_allocation.py`

**Interfaces:**
- Consumes: `AllocationRunDbRepository.list_runs/get_run`（Task 10）
- Produces: `GET /api/v1/tasks/runs`、`GET /api/v1/tasks/runs/{run_id}`

> **路由顺序注意**：`/{run_id}` 这类通配路由必须注册在 `/algorithms` 之后，否则 `/tasks/runs` 会被更早注册的同级路由抢先匹配。

- [ ] **Step 1: 加 schema**

`src/schemas/task_allocation.py` 末尾追加：

```python
class AllocationRunSummary(BaseModel):
    """一次分配运行的摘要"""
    id: UUID
    algorithm: str
    params: dict | None = None
    uav_count: int
    task_count: int
    assigned_count: int
    unassigned_count: int
    unassigned_task_ids: list[str] = Field(default_factory=list)
    duration_ms: float | None = None
    created_at: datetime


class AllocationRunListResponse(BaseModel):
    runs: list[AllocationRunSummary]
    total: int


class AllocationRunDetailResponse(AllocationRunSummary):
    """明细：含该次运行的 uav→task 配对"""
    allocations: list[TaskAllocation]
```

顶部导入改为：

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models import UAV, Task, TaskAllocation
```

- [ ] **Step 2: 加端点**

`src/api/v1/endpoints/task_allocation.py` 末尾追加：

```python
@router.get("/runs", response_model=AllocationRunListResponse)
async def list_allocation_runs(algorithm: str | None = None, limit: int = 50) -> AllocationRunListResponse:
    """列出历史分配运行（按时间倒序）"""
    repo = result_repo("allocation")
    if repo is None:
        raise HTTPException(status_code=503, detail="未启用数据库持久化，无法查询历史运行")
    runs = await repo.list_runs(algorithm=algorithm, limit=limit)
    # total 必须用独立 COUNT 查询：list_runs 内部有 SQL LIMIT，
    # len(runs) 会把被截断的数量当总数（超过 limit 时错误）
    total = await repo.count_runs(algorithm=algorithm)
    return AllocationRunListResponse(runs=runs, total=total)


@router.get("/runs/{run_id}", response_model=AllocationRunDetailResponse)
async def get_allocation_run(run_id: UUID) -> AllocationRunDetailResponse:
    """查询单次分配运行的明细"""
    repo = result_repo("allocation")
    if repo is None:
        raise HTTPException(status_code=503, detail="未启用数据库持久化，无法查询历史运行")
    detail = await repo.get_run(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"分配运行 {run_id} 不存在")
    return AllocationRunDetailResponse(**detail)
```

并在导入区补 `from uuid import UUID` 与 `from src.schemas.task_allocation import (AllocateRequest, AllocateResponse, AllocationRunListResponse, AllocationRunDetailResponse)`。

- [ ] **Step 3: 确认 memory 模式下返回 503 而非 500**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS。手工核对：memory 模式下 `GET /tasks/runs` 返回 503

- [ ] **Step 4: 连真库验证读端点**

Run（需 `UAV_REPOSITORY_BACKEND=db` 且迁移已执行）：
```bash
.venv/Scripts/python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000 &
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks/allocate -H "Content-Type: application/json" -d '{"uavs":[{"id":"u1","position":{"x":0,"y":0},"speed":10,"max_payload":5,"battery":1000}],"tasks":[{"id":"t1","position":{"x":10,"y":0},"payload_weight":1}],"algorithm":"hungarian"}'
curl -s "http://127.0.0.1:8000/api/v1/tasks/runs?algorithm=hungarian"
```
Expected: 第一条返回 allocations；第二条返回含 1 条 run 的列表，`assigned_count` 与第一次调用一致

- [ ] **Step 5: 提交**

```bash
git add src/schemas/task_allocation.py src/api/v1/endpoints/task_allocation.py
git commit -m "feat(python-db): 添加分配运行历史读端点"
```

---

## Phase 5 — 收尾与端到端验证

### Task 14: 基础设施、文档与端到端验证

**Files:**
- Modify: `infra/db/init.sql`、`.env.example`、`src/main.py`、`README.md`

**Interfaces:**
- Consumes: 全部前置任务
- Produces: 可复现的环境说明与清理逻辑

- [ ] **Step 1: 修正 init.sql**

`infra/db/init.sql` 全文替换为：

```sql
-- PostgreSQL 初始化脚本 — 启用 PostGIS + pgvector 扩展
--
-- 注意：本文件只负责扩展。表结构由 Alembic 管理（apps/server/python-fastapi-backend/alembic/），
-- 不要在此处添加建表语句，否则会与迁移产生两套 DDL 来源。
--
-- 【Docker 环境警告】docker-compose 当前使用的 pgvector/pgvector:pg16 镜像
-- 只含 pgvector、不含 PostGIS，执行下面的 CREATE EXTENSION postgis 会失败。
-- 需要改为自带 PostGIS 的镜像，例如：
--     FROM pgvector/pgvector:pg16
--     RUN apt-get update && apt-get install -y --no-install-recommends \
--         postgresql-16-postgis-3 && rm -rf /var/lib/apt/lists/*
-- 或直接使用同时打包两者的现成镜像。

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS vector;
```

- [ ] **Step 2: 补 .env.example**

在「Python 后端」小节追加：

```bash
# 存储后端：memory = 内存仓储（无需数据库）；db = PostgreSQL
UAV_REPOSITORY_BACKEND=db
# 算法结果是否落库；off 时端点跳过写库
UAV_PERSIST_RESULTS=on
```

并把文件头的数据库小节说明改为：后端目录下可另放一份 `.env`，其优先级高于仓库根 `.env`。

- [ ] **Step 3: main.py 关闭时释放引擎**

`src/main.py` 的 `lifespan` 中，把 shutdown 段的占位注释替换为：

```python
    _log("[*] Closing database connections...")
    if settings.repository_backend == "db":
        from src.db.engine import engine
        await engine.dispose()
        _log("[OK] Database engine disposed.")
    _log("[OK] Cleanup done. Server stopped cleanly.")
```

- [ ] **Step 4: 更新 README**

`apps/server/python-fastapi-backend/README.md`：

- 「ORM 模型」小节的 ER 图从 3 张表扩到 10 张，标注每张表的写入方（Python / 将来 Node）
- 「数据库」小节把 `alembic upgrade head` 的说明补全为：先建库、再设 `UAV_DATABASE_URL`、再迁移；并删除或更正 `uv run dev` / `uv run test` / `uv run lint` 这些**不可执行**的命令（改为 `uvicorn src.main:app ...` / `pytest tests/ -q` / `ruff check src/`）
- 「环境安装」小节（现教 `uv sync`，而 `uv.lock` 未入 git 且与 `[project.scripts]` 一样不可靠）：先 `uv venv` 建虚拟环境，再说明 dev 依赖（含本计划新增的 `pytest-asyncio`）用 `.venv/Scripts/python.exe -m pip install -e ".[dev]"` 或 `uv pip install -e ".[dev]"` 安装，不要教 `uv sync`（注意：`uv pip install --extra dev` 在 uv 0.12.9 下无效，勿用）
- 新增「持久化开关」小节，说明 `UAV_REPOSITORY_BACKEND` 与 `UAV_PERSIST_RESULTS` 的取值与默认

- [ ] **Step 5: 端到端验证**

Run（`.env` 设 `UAV_REPOSITORY_BACKEND=db`）：
```bash
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8000 &
```

依次打端点并核对落库：

```bash
# ① 注册无人机 -> uavs
curl -s -X POST http://127.0.0.1:8000/api/v1/uavs -H "Content-Type: application/json" \
  -d '{"id":"uav-e2e","x":1.0,"y":2.0,"z":30.0,"speed":10.0,"max_payload":5.0,"battery":1000.0}'
psql -U postgres -h localhost -d st_risk -c "SELECT id, ST_AsText(position), status FROM uavs WHERE id='uav-e2e';"
# 期望：POINT Z (1 2 30)，status=idle

# ④ 任务分配 -> allocation_runs + allocation_items
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks/allocate -H "Content-Type: application/json" \
  -d '{"uavs":[{"id":"uav-e2e","position":{"x":1,"y":2,"z":30},"speed":10,"max_payload":5,"battery":1000}],"tasks":[{"id":"t-e2e","position":{"x":11,"y":2},"payload_weight":1}],"algorithm":"hungarian"}'
psql -U postgres -h localhost -d st_risk -c "SELECT algorithm, assigned_count, duration_ms FROM allocation_runs ORDER BY created_at DESC LIMIT 1;"
psql -U postgres -h localhost -d st_risk -c "SELECT count(*) FROM allocation_items WHERE run_id = (SELECT id FROM allocation_runs ORDER BY created_at DESC LIMIT 1);"
# 期望：assigned_count 与 items 行数一致

# ⑥ 监控快照 -> flight_snapshots（含异常时的 flight_alerts）
curl -s -X POST http://127.0.0.1:8000/api/v1/monitoring/snapshot -H "Content-Type: application/json" \
  -d '{"uav_id":"uav-e2e","x":1.0,"y":2.0,"z":30.0,"battery_remaining":8.0,"speed":12.0,"heading":90.0,"timestamp":1.0}'
psql -U postgres -h localhost -d st_risk -c "SELECT uav_id, ts, is_anomaly, anomaly_reasons FROM flight_snapshots ORDER BY id DESC LIMIT 1;"
psql -U postgres -h localhost -d st_risk -c "SELECT uav_id, message FROM flight_alerts ORDER BY id DESC LIMIT 3;"
# 期望：is_anomaly=true，anomaly_reasons 含电量告警；flight_alerts 有对应行
```

- [ ] **Step 6: 回归确认 memory 模式仍可用**

Run：`.env` 改回 `UAV_REPOSITORY_BACKEND=memory`，然后 `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部 PASS，服务在无库配置下也能启动

- [ ] **Step 7: 提交**

```bash
git add infra/db/init.sql .env.example apps/server/python-fastapi-backend/src/main.py apps/server/python-fastapi-backend/README.md
git commit -m "docs(python-db): 修正 init.sql、补配置示例与 README，关闭时释放引擎"
```

---

## 自查记录

**Spec 覆盖核对**

| Spec 章节 | 对应任务 |
|---|---|
| §3.1 init.sql 修正 | Task 14 |
| §4 A 组表 | Task 3 |
| §4 B 组表 | Task 4 |
| §4 C 组表 | Task 5 |
| §4.1 索引 | Task 7 |
| §5 迁移方案 | Task 6、7 |
| §6.1 接口 async | Task 8 |
| §6.2 SQLAlchemy 仓储 | Task 10 |
| §6.3 映射层 | Task 9 |
| §6.4 工厂与配置 | Task 2、11 |
| §6.5 波及的 service | Task 8、11 |
| §7.1 落库位置与 500 语义 | Task 12 |
| §7.2 读端点 | Task 13 |
| §8 测试 | Task 1、9、10 |
| §9 验证步骤 | Task 7 Step 5-7、Task 13 Step 4、Task 14 Step 5 |
| §8.3 pytest-asyncio | Task 1 |

**已知偏差**

- Spec §8.1 说 `test_services.py` 的六个调用点需改；计划 Task 8 Step 5 进一步细化为「仅 `uav_resource` / `flight_monitoring` 相关用例改 async，`evaluate`/`assess` 相关用例保持同步」。
- Spec §6.1 说「全仓库共 5 个测试文件」，计划执行后新增 `test_config.py` / `test_mappers.py` / `test_repository_factory.py` / `test_db_persistence.py`，共 9 个。
