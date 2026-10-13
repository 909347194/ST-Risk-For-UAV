# Python 后端持久化落地 — 设计文档

日期：2026-10-13
分支：feat/python-db-persistence（起点 feat/python-api-backend @ 4834ab6）
范围：**仅 Python 后端**，Node 后端本轮不动

## 1. 背景与目标

Python 后端当前处于「数据库骨架搭好、但一根线都没接上」的状态：

- `src/db/engine.py` 有 async engine + `AsyncSessionLocal` + `get_db`，但 **`get_db` 零调用**
- `src/db/base.py` 有 `DeclarativeBase`；`src/db/models/` 下有 3 个模型（`uavs` / `tasks` / `flight_logs`）
- `allocation.py` 与 `risk_record.py` 是**空文件**，且在 `models/__init__.py` 里被注释掉
- 6 个业务模块的 service **全部使用模块级单例内存仓储**（`InMemoryRepository`）；其中 ④⑤ 任务分配/航线规划、②③ 适配/风险评估这四个模块完全无状态
- `pyproject.toml` 有 `alembic>=1.14`，但**没有 `alembic.ini`、没有迁移目录** —— README 中 `alembic upgrade head` 等命令必然失败
- `infra/db/init.sql` 只有三句 `CREATE EXTENSION`，没有任何建表语句，且**在两个环境下都跑不通**（见 §3）

目标：把 Python 后端从内存存储切到 PostgreSQL，使算法产出与运行时数据可持久化、可查询，为算法对比实验提供数据基础。

## 2. 已确认的决策

| 决策点 | 结论 |
|---|---|
| 表归属 | Python 建**全部**表；语义上 **Python 是结果表的写入方**，`uavs` / `tasks` 将来由 Node 写入、Python 只读。归属在模型 docstring 与迁移注释中显式标注 |
| 建表范围 | 10 张表一次建齐（A 组 2 + B 组 5 + C 组 3） |
| 结果表粒度 | **混合**：任务分配用 run + 明细两层（支撑 DE / CW / 匈牙利 / 拍卖横向对比）；适配评估、风险评估、航线规划用扁平记录表 |
| 监控表拆分 | `flight_snapshots`（逐点快照）与 `flight_alerts`（告警）**分两张**，不合表（两者写入频率、查询方式、保留策略不同，合表会让快照表被两类语义污染） |
| `flight_logs` | 建表但标注「**暂无写入方**」，不硬造「飞行会话」概念 |
| 仓储策略 | **双实现 + 配置切换**：接口统一 async，保留内存实现供单测/无库开发，新增 SQLAlchemy 实现 |
| 本地库 | 本机原生 PostgreSQL 18.3（非 Docker） |
| pgvector | **由用户手动编译安装**；装好之前不执行迁移 |
| 迁移工具 | Alembic 异步模板；本轮 DDL 权威唯一归 Alembic（Node 侧 Drizzle 不动） |
| 写库失败语义 | **默认让请求 500**，避免静默丢失实验数据；另给 `UAV_PERSIST_RESULTS=off` 开关用于无库开发 |
| 读端点 | 仅补任务分配一条线（runs 列表 + 明细）；其余表暂用 psql 直接查，有需求再加 |

## 3. 数据库环境现状（实测于 2026-10-13）

| 项 | 状态 |
|---|---|
| 本机 PostgreSQL | **18.3**，监听 `0.0.0.0:5432`（原生安装，非容器） |
| psql 客户端 | 18.3，在 PATH 上 |
| PostGIS | ✅ **3.6.2 可用**（`postgis_topology` 3.6.2 亦可用） |
| pgvector | ❌ **未安装** —— `pg_available_extensions` 中查不到 `vector` |
| Docker | 29.5.3 已装，但 **Docker Desktop 守护进程未启动** |
| `.env` 的 `DATABASE_URL` | 密码对本机 5432 **认证失败**，说明该配置是照 Docker 容器写的；本机库需另行配置连接串 |

### 3.1 需要一并修正的两个基础设施问题

1. **`infra/db/init.sql` 在本机环境不可用**：本机缺 pgvector，`CREATE EXTENSION vector` 会失败。
2. **同一文件在 Docker 环境也不可用**：compose 使用的 `pgvector/pgvector:pg16` 镜像**只含 pgvector、不含 PostGIS**（官方镜像基于 `postgres:16` 仅添加 vector 扩展），因此第一句 `CREATE EXTENSION postgis` 就会失败。

修正方向：`init.sql` 改为与本机开发对齐（扩展清单与 §5 迁移一致），并在文件头注明 Docker 镜像需要换成自带 PostGIS 的版本（`FROM pgvector/pgvector:pg16` + `apt-get install postgresql-16-postgis-3`，或使用现成的组合镜像）。这是独立于本设计的一个小修正，随本轮一起提交。

## 4. 表结构

命名沿用现有风格（复数、snake_case）。所有表加 `created_at`；主数据表另加 `updated_at`。

### A 组 — 主数据表（标注：**将来 Node 写入，Python 只读**）

| 表 | 列 |
|---|---|
| `uavs` | `id` TEXT PK · `position` geometry(POINT_Z, 4326) NOT NULL · `speed` REAL · `max_payload` REAL · `battery` REAL · `status` TEXT DEFAULT `'idle'` · 时间戳 |
| `tasks` | `id` TEXT PK · `position` geometry(POINT_Z, 4326) NOT NULL · `priority` TEXT DEFAULT `'medium'` · `payload_weight` REAL · `time_limit` DOUBLE PRECISION NULL · `status` TEXT DEFAULT `'pending'` · 时间戳 |

两处与 Node 侧现有模型的对齐说明：

- `tasks.time_limit` **采用 Python 的 `float`**（Node 侧写的是 `integer`）。浮点能无损容纳整数，反之会截断；领域模型 `Task.time_limit: float | None` 也是浮点。
- `tasks.status` **补上**（Node 侧有、Python 侧漏了）。补一列的成本为零，可避免将来两端继续漂移。

### B 组 — 算法结果表（Python 写入）

| 表 | 粒度 | 列 |
|---|---|---|
| `allocation_runs` | 一次 `/tasks/allocate` 调用 | `id` UUID PK · `algorithm` TEXT · `params` JSONB · `uav_count` INT · `task_count` INT · `assigned_count` INT · `unassigned_count` INT · `unassigned_task_ids` JSONB · `duration_ms` DOUBLE PRECISION · `created_at` |
| `allocation_items` | 该次调用里的一条 uav→task 配对 | `id` BIGSERIAL PK · `run_id` UUID FK→`allocation_runs` ON DELETE CASCADE · `uav_id` TEXT · `task_id` TEXT · `estimated_cost` DOUBLE PRECISION |
| `adaptability_results` | 一次 `/adaptability/evaluate` | `id` BIGSERIAL PK · `uav_id` · `task_id` · `capable` · `payload_ok` · `battery_ok` · `range_ok` · `time_ok` BOOL · `score` DOUBLE PRECISION · `reasons` JSONB · `created_at` |
| `risk_records` | 一次 `/risk/assess` | `id` BIGSERIAL PK · `uav_id` · `task_id` · `risk_level` TEXT · `collision_risk` · `weather_risk` · `battery_risk` · `overall_score` · `weather_factor` DOUBLE PRECISION · `details` JSONB · `created_at` |
| `path_plans` | 一次 `/paths/plan` | `id` BIGSERIAL PK · `uav_id` · `task_id` · `algorithm` TEXT · `waypoints` JSONB · `total_distance` · `estimated_time` · `duration_ms` DOUBLE PRECISION · `created_at` |

`allocation_runs` + `allocation_items` 即「混合粒度」的落点：**run 存算法对比所需的指标，items 存配对明细**，按 `algorithm` 分组即可横向比较各算法的分配数、未分配数与耗时。

`path_plans.waypoints` 用 JSONB 而非 PostGIS 线几何 —— 它直接对应领域模型 `PathPlan.waypoints: list[Waypoint]`（含每点到达时间），转成几何会丢失时间维度。若将来需要按航线做空间查询，再补一个由 waypoints 派生的 `LINESTRING Z` 列。

### C 组 — 运行时/监控表（Python 写入）

| 表 | 说明 | 列 |
|---|---|---|
| `flight_snapshots` | **新增**，对应 `FlightLogRepository._tracks` | `id` BIGSERIAL PK · `uav_id` TEXT · `ts` DOUBLE PRECISION · `position` geometry(POINT_Z, 4326) · `battery_remaining` REAL · `speed` REAL · `heading` REAL · `is_anomaly` BOOL · `anomaly_reasons` JSONB · `created_at` |
| `flight_alerts` | **新增**，对应 `_alerts` | `id` BIGSERIAL PK · `uav_id` TEXT · `message` TEXT · `created_at` |
| `flight_logs` | **已有模型，暂无写入方** | `id` TEXT PK · `uav_id` TEXT · `track` geometry(LINESTRING Z, 4326) · `embedding` vector(128) · `start_time` / `end_time` TIMESTAMPTZ · `total_distance` DOUBLE PRECISION |

`flight_snapshots.ts` 用 `DOUBLE PRECISION` 而非 `TIMESTAMPTZ`：领域模型 `UAVHealthSnapshot.timestamp: float` 是仿真时间戳（秒），不是墙钟时间；改用时间类型会丢掉仿真语义。

### 4.1 索引

- 所有 geometry 列建 **GIST** 索引（geoalchemy2 对 `Geometry` 列默认 `spatial_index=True`，但 autogenerate 对这类「建表语句之外」的索引检测不稳定，生成后需逐条核对）
- `flight_logs.embedding` 建 **HNSW** 索引（`vector_l2_ops`）
- B-tree：`allocation_items(run_id)`、`allocation_items(uav_id)`、`allocation_items(task_id)`、`risk_records(uav_id, created_at)`、`flight_snapshots(uav_id, ts)`、`flight_alerts(uav_id, created_at)`、`allocation_runs(algorithm, created_at)`

## 5. 迁移方案（Alembic）

### 5.1 配置

- `alembic.ini`：只放通用配置（`script_location`、带日期的 `file_template`），**URL 不写死**
- `alembic/env.py`：异步模板（`alembic init -t async`），URL 从 `src.utils.config.get_settings()` 读取 —— 保证 `.env` 与 `UAV_` 前缀只有一处配置来源，杜绝「应用连 A 库、迁移连 B 库」

  > 注意：`Settings` 的 `env_prefix="UAV_"` 会把 `.env` 里的变量按 `UAV_` 前缀匹配，而 alembic 自身也读环境变量。env.py 中需显式取 `settings.database_url` 并赋给 `config.set_main_option("sqlalchemy.url", ...)`，避免 alembic 的 `%` 插值把 DSN 里的字符当格式符。

- `env.py` 必须 `from src.db.models import *`（且 `models/__init__.py` 需把 10 张表全部导出）。**漏掉任何模型，autogenerate 都会认为库里没有该表，进而生成 `DROP TABLE`。**

### 5.2 初始迁移

用 `alembic revision --autogenerate` 起手，**生成后必须人工修改**：

1. 在 `upgrade()` 最前面补：
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
   几何列与向量列的类型依赖扩展先存在。`CREATE EXTENSION` 需要超级用户权限（PostGIS **不是** trusted 扩展），因此连接账号须为 `postgres`。
2. 核对 GIST 索引是否齐全（见 §4.1 的说明）
3. 手动补 `embedding` 的 HNSW 索引与其余 B-tree 索引

`downgrade()` **只 DROP TABLE，不 DROP EXTENSION** —— 扩展是实例级对象，删掉会影响同实例的其他库。

### 5.3 前置条件

迁移执行前需要：

1. 用户完成 pgvector 的手动安装（见 §9）
2. `st_risk` 数据库已存在（`CREATE DATABASE st_risk;`）
3. `.env` 里的 `UAV_DATABASE_URL` 指向**本机** 5432 且密码正确（现有配置对本机认证失败，需先修正）

## 6. 仓储改造

### 6.1 接口改 async

`BaseRepository` 的 5 个方法（`save` / `find_by_id` / `find_all` / `delete` / `exists`）全部改为 `async def`；`InMemoryRepository` 保持 dict 实现、仅加 `async`。

**对现有测试的影响（实测核对，见 §8.1）**：走 HTTP 边界的测试完全不受影响（`TestClient` 自己驱动事件循环）；但 `tests/test_services.py` **直接同步调用** `uav_resource` 与 `flight_monitoring` 的 service 函数，这两个模块改成 `async def` 后该文件必须跟着改。全仓库共 5 个测试文件，其中**只有这一个需要修改**。

### 6.2 新增 SQLAlchemy 实现

- 每个需要持久化的模块一个具体仓储（`UAVDbRepository`、`FlightLogDbRepository` 等），构造时接收 `async_sessionmaker`
- **每个方法开一个短会话**（`async with factory() as session: ...; await session.commit()`），使 session 不渗透到 service 层签名；service 的参数与返回值仍为领域模型
- 事务边界即方法边界。本项目没有跨仓储的原子操作需求，这个粒度足够

### 6.3 映射层（必须）

新增 `src/repositories/mappers.py`，负责领域模型 ↔ ORM 模型互转：

- `Position(x, y, z)` ↔ PostGIS `POINT_Z`（WKT 或 WKBElement）
- `UAVStatus` / `TaskPriority` / `RiskLevel` 枚举 ↔ `str`
- `reasons` / `details` / `anomaly_reasons` 的 `list[str]` ↔ JSONB
- `RiskAssessment` → `risk_records` 行的字段铺平

没有这层，ORM 对象会一路漏进 service 与响应模型。

### 6.4 工厂与配置开关

- `src/utils/config.py` 新增：
  - `repository_backend: Literal["memory", "db"] = "memory"`（环境变量 `UAV_REPOSITORY_BACKEND`）
  - `persist_results: bool = True`（环境变量 `UAV_PERSIST_RESULTS`）
- `src/repositories/factory.py`：按 `settings.repository_backend` 返回实现

**默认 `memory`**：没库也能起服务、跑测试，与现状一致；本地验真库时在 `.env` 里切 `db`。

### 6.5 波及的 service

- `uav_resource/service.py`、`flight_monitoring/service.py`：现有函数改 `async def`（因为它们调用仓储），端点加 `await`。注意这两个模块目前是 `_repo = XxxRepository()` 模块级单例，需改为通过工厂获取
- ②③④⑤ 四个纯算法模块的 service **保持不变**（纯函数，不起会话）

## 7. 写入触发点与读端点

### 7.1 结果落库位置

放在 **endpoint 层**（它本来就是编排层），service 保持纯函数、继续好测。端点流程变为「算 → 存 → 组装响应」。

**写库失败语义：默认让请求返回 500。** 理由：本项目的数据服务于算法对比实验，静默丢数据远比报错危险 —— 若写库失败仍返回 200，会误以为实验数据已落库，等问题在写论文阶段才暴露。无库开发时用 `UAV_PERSIST_RESULTS=off` 关闭持久化。

启动时 `duration_ms` 由端点侧计时得出并写入（不污染算法层）。

### 7.2 读端点（仅分配线）

- `GET /tasks/runs` — 按 `algorithm` / 时间范围筛选的 run 列表
- `GET /tasks/runs/{run_id}` — 单个 run 的明细（含 `allocation_items`）

其余三张结果表本轮不加读端点，用 psql 直接查询；等前端或分析脚本提出具体查询需求再加，避免凭猜测设计接口。

## 8. 测试计划

### 8.1 现有测试（5 个文件，逐一核对过）

| 文件 | 调用方式 | 是否需改 |
|---|---|---|
| `test_api_error_mapping.py` | `TestClient` 打 HTTP | ❌ 不动 |
| `test_api_task_allocation.py` | `TestClient` 打 HTTP | ❌ 不动 |
| `test_path_planning.py` | 直接调 `route_planning.plan_path`（保持同步） | ❌ 不动 |
| `test_task_allocation.py` | 直接调 `task_allocation.allocate`（保持同步） | ❌ 不动 |
| `test_services.py` | 直接调 `uav_resource` / `flight_monitoring` 的**同步**函数 | ✅ **必须改** |

`test_services.py` 需要改造的点：`register_uav` / `get_uav` / `list_uavs` / `update_uav_status` / `record_snapshot` / `get_track` 六个调用点。该文件里其余调用（`evaluate`、`evaluate_all`、`assess`）属于保持同步的纯算法模块，不用动。

### 8.2 新增

- `tests/test_db_persistence.py`，打 `@pytest.mark.integration` 标记
  - 分配结果写入后能按 `run_id` 读回，且 `allocation_items` 条数与 `assigned_count` 一致
  - 映射层往返：领域模型 → ORM → 领域模型，`Position` 的 z 分量、枚举、`list[str]` 不丢
  - `unassigned_task_ids` 往返正确
- `pyproject.toml` 增加 pytest 配置：注册 `integration` 标记 + `addopts = "-m 'not integration'"`，保证默认 `pytest` 不连库；同时设 `asyncio_mode = "auto"`

### 8.3 新增依赖

dev 依赖组目前只有 `pytest` / `httpx` / `ruff`，**没有异步测试支持**。改造后 `test_services.py` 与新增的集成测试都要 `await` 协程，需补：

- **`pytest-asyncio`** —— 不采用「在同步测试里手写 `asyncio.run(...)`」的绕法，那样每个调用点都要包一层，且异常栈会被吃掉一层

（`anyio` 随 Starlette 传递依赖已在环境里、自带 pytest 插件，但依赖传递依赖不稳定，不走这条路。）

**这些测试要等你装完 pgvector 才能跑。** PostGIS/pgvector 表无法用 SQLite 顶替。

## 9. 验证步骤

前置：用户手动安装 pgvector（Windows 无预编译包，需 VS C++ 生成工具 + `nmake /F Makefile.win`，装 v0.8.6+ 以支持 PG 18）。

1. 确认扩展已就位：
   ```sql
   SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis','vector');
   ```
2. 建库并修正 `.env` 的本机连接串
3. `alembic upgrade head`
4. `\dt` 核对 10 张表齐全；抽查关键列类型（`position` 应为 `geometry(PointZ,4326)`、`embedding` 应为 `vector(128)`）
5. `.env` 设 `UAV_REPOSITORY_BACKEND=db`，起服务
6. 打一遍 `/tasks/allocate`、`/risk/assess`、`/monitoring/snapshot`
7. psql 查各表确认落库，核对 `allocation_runs.assigned_count` 与 `allocation_items` 行数一致

## 10. 不在本轮范围

- Node 后端持久化（Drizzle 配置、`/api/v1/uavs` 控制器）
- 特征提取与 embedding 生成（`flight_logs.embedding` 本轮只建列，没有写入方）
- 轨迹相似度检索接口
- Redis / arq 任务队列
- `uavs` / `tasks` 的写权限移交 Node（本轮仍由 Python 端点写入，待 Node 侧就绪后再退化 Python 为只读）
