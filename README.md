# ST-Risk-For-UAV

无人机时空风险评估与任务分配系统 — Monorepo

## 项目全景

```
.
├── apps/                          # 应用层
│   ├── client/
│   │   └── web-frontend/          # Vue 3 + TypeScript + Pinia
│   └── server/
│       ├── node-backend/          # NestJS + Drizzle ORM（Agent 服务）
│       └── python-fastapi-backend/ # FastAPI + SQLAlchemy（算法服务）
│
├── packages/                      # 共享包
│   └── shared-ts/                 # 前后端共享类型、枚举、工具
│
├── infra/                         # 基础设施
│   ├── docker/                    # Dockerfile + docker-compose
│   ├── db/                        # 数据库初始化 + 迁移
│   └── nginx/                     # 反向代理
│
├── docs/                          # 项目文档
│   ├── architecture/              # 架构文档 + 技术选型决策
│   ├── algorithms/                # 算法设计文档
│   ├── api/                       # API 文档
│   ├── deployment/                # 部署指南
│   └── research/                  # 论文/研究
│
├── experiments/                   # 实验
└── paper/                         # 论文（待整理）
```

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| Node 后端 | NestJS + TypeScript + Drizzle ORM + Zod |
| Python 后端 | FastAPI + SQLAlchemy 2.0（异步）+ Alembic |
| 数据库 | PostgreSQL + PostGIS + pgvector |
| 共享类型 | TypeScript（@st-risk/shared-ts） |
| 包管理 | pnpm（monorepo workspace）+ uv（Python） |
| 容器化 | Docker + docker-compose |

## 服务关系

```mermaid
graph LR
    FE[前端 :5173] -->|HTTP| NODE[Node :3000]
    NODE -->|HTTP| PY[Python :8000]
    NODE -->|SQL| DB[(PostgreSQL)]
    PY -->|SQL| DB

    FE -.->|共享类型| SHARED[shared-ts]
    NODE -.->|共享类型| SHARED
```

- **前端**：UI 交互、可视化
- **Node 后端**：Agent 编排、业务流程、数据持久化
- **Python 后端**：算法计算（路径规划、任务分配、风险评估）
- **PostgreSQL**：统一数据存储（PostGIS 空间 + pgvector 向量）

## 快速开始

### Docker 一键启动

```bash
cd infra/docker
docker compose up -d
```

- 前端：http://localhost
- Node 后端：http://localhost:3000
- Python 后端：http://localhost:8000

### 本地开发

```bash
# 安装依赖
pnpm install

# 启动 Python 后端
cd apps/server/python-fastapi-backend
uv sync && uv run uvicorn src.main:app --reload

# 启动 Node 后端
pnpm --filter @st-risk/node-backend dev

# 启动前端
pnpm --filter @st-risk/web-frontend dev
```

## 各端 README

- [前端](apps/client/web-frontend/README.md)
- [Node 后端](apps/server/node-backend/README.md)
- [Python 后端](apps/server/python-fastapi-backend/README.md)
- [基础设施](infra/README.md)

## 文档

- [架构概览](docs/architecture/README.md)
- [技术选型决策](docs/architecture/decisions/)
- [算法设计](docs/architecture/algorithms/)
- [部署指南](docs/deployment/)
