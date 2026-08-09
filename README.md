# ST-Risk-For-UAV

基于时空风险分析的无人机风险评估系统。

## 技术栈

| 层级 | 技术 | 包管理 | 说明 |
|------|------|--------|------|
| 前端 | TypeScript | pnpm | Web 应用 |
| 后端 A | Python 3.12 + FastAPI | uv | 无人机任务分配 / 路径规划 |
| 后端 B | TypeScript + Node.js | pnpm | 待定 |
| 共享层 | TypeScript / Python | pnpm / uv | 类型定义、工具函数、数据模型 |
| 数据库 | PostgreSQL | — | 规划中 |

> **两个后端是独立、并列的服务**，各自承担不同职责，可独立部署和扩展。

## 项目结构

```
ST-Risk-For-UAV/
├── apps/
│   ├── client/
│   │   └── web-frontend/                  # 前端应用 (TypeScript)
│   └── server/
│       ├── python-fastapi-backend/        # 后端 A — 任务分配 & 路径规划
│       │   ├── src/
│       │   │   ├── main.py                # FastAPI 入口
│       │   │   ├── task_allocation/       # 任务分配领域
│       │   │   │   ├── router.py          #   API 路由
│       │   │   │   ├── schemas.py         #   请求/响应模型
│       │   │   │   ├── service.py         #   业务编排
│       │   │   │   └── algorithms/        #   核心算法
│       │   │   │       ├── hungarian.py   #     匈牙利算法
│       │   │   │       └── auction.py     #     拍卖算法
│       │   │   ├── path_planning/         # 路径规划领域
│       │   │   │   ├── router.py
│       │   │   │   ├── schemas.py
│       │   │   │   ├── service.py
│       │   │   │   └── algorithms/
│       │   │   │       ├── astar.py       #     A* 算法
│       │   │   │       └── rrt.py         #     RRT 快速随机树
│       │   │   └── shared/                # 跨领域共享
│       │   │       ├── models.py          #   UAV, Task, Position 等领域模型
│       │   │       └── utils.py           #   几何计算工具
│       │   ├── tests/                     # 测试
│       │   └── pyproject.toml             # Python 依赖配置
│       └── node-backend/                  # 后端 B — TypeScript + Node.js
├── packages/
│   ├── shared-ts/                         # 共享 TypeScript 代码
│   │   └── src/
│   │       ├── types/                     #   类型定义
│   │       ├── api/                       #   API 请求封装
│   │       └── utils/                     #   工具函数
│   └── shared-py/                         # 共享 Python 代码
│       └── src/
│           └── shared_py/
├── scripts/                               # 自动化脚本
├── docs/                                  # 项目文档
│   └── CONTRIBUTING.md                    #   协作指南
├── package.json                           # pnpm 根配置
├── pnpm-workspace.yaml                    # pnpm 工作区定义
├── pyproject.toml                         # uv / Python 根配置
├── tsconfig.base.json                     # TypeScript 基础配置
└── uv.lock                                # uv 锁文件
```

## 架构说明

```
┌─────────────┐
│   前端 (Web) │
└──────┬──────┘
       │
       ├──────────────────┐
       ▼                  ▼
┌──────────────┐   ┌──────────────┐
│  Python 后端  │   │  Node 后端    │
│  FastAPI      │   │  TypeScript   │
│  任务分配      │   │  待定          │
│  路径规划      │   │              │
└──────┬───────┘   └──────┬───────┘
       │                  │
       └────────┬─────────┘
                ▼
        ┌──────────────┐
        │  PostgreSQL   │  (规划中)
        │  共享数据库    │
        └──────────────┘
```

- **Python 后端**：无人机任务分配算法（匈牙利、拍卖）和路径规划算法（A*、RRT），对外暴露 REST API
- **Node 后端**：待定
- 两者独立部署，互不耦合

### Python 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tasks/allocate` | 提交任务分配请求 |
| GET | `/api/v1/tasks/algorithms` | 列出可用分配算法 |
| POST | `/api/v1/paths/plan` | 提交路径规划请求 |
| GET | `/api/v1/paths/algorithms` | 列出可用规划算法 |
| GET | `/health` | 健康检查 |

## 快速开始

### 环境要求

- **Node.js** ≥ 18
- **pnpm** ≥ 10
- **Python** ≥ 3.12
- **uv** ≥ 0.4

### 安装依赖

```bash
# Node 依赖（根目录，包含所有 workspace 包）
pnpm install

# Python 依赖（进入 Python 后端目录）
cd apps/server/python-fastapi-backend
uv sync --extra dev
```

### 运行

```bash
# Python 后端（FastAPI + uvicorn）
cd apps/server/python-fastapi-backend
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Node 后端
pnpm --filter node-backend dev

# 前端（开发模式）
pnpm --filter web dev
```

### 测试

```bash
# Python 后端测试
cd apps/server/python-fastapi-backend
uv run pytest tests/ -v
```

## 开发指南

### 添加前端 / Node 依赖

```bash
pnpm --filter <package-name> add <dependency>
```

### 添加 Python 依赖

```bash
# 进入 Python 后端目录
cd apps/server/python-fastapi-backend
uv add <package>

# 开发依赖
uv add --extra dev <package>
```

### 工作区结构

- **pnpm workspace** 管理所有 TypeScript/Node 包（前端 + Node 后端 + shared-ts）
- **uv** 管理所有 Python 包（Python 后端 + shared-py）
- TypeScript 包之间通过 `workspace:*` 协议互引
- Python 子包通过 uv 虚拟环境统一管理

## 协作流程

小团队轻量协作，详见 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)

## 文档

- [协作指南](docs/CONTRIBUTING.md) — 分支策略、代码规范、PR 流程
- [文档目录](docs/) — 设计文档、架构决策
