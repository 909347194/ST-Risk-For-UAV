# ST-Risk-For-UAV

基于时空风险分析的无人机风险评估系统。

## 技术栈

| 层级 | 技术 | 包管理 | 说明 |
|------|------|--------|------|
| 前端 | TypeScript | pnpm | Web 应用 |
| 后端 A | Python 3.12 + FastAPI | uv | 数据分析 / 模型计算服务 |
| 后端 B | TypeScript + Node.js | pnpm | 业务 API / 实时服务 |
| 共享层 | TypeScript / Python | pnpm / uv | 类型定义、工具函数、数据模型 |
| 数据库 | PostgreSQL | — | 规划中 |

> **两个后端是独立、并列的服务**，各自承担不同职责，可独立部署和扩展。

## 项目结构

```
ST-Risk-For-UAV/
├── apps/
│   ├── client/
│   │   └── web-frontend/              # 前端应用 (TypeScript)
│   └── server/
│       ├── python-fastapi-backend/    # 后端 A — Python + FastAPI
│       └── node-backend/              # 后端 B — TypeScript + Node.js
├── packages/
│   ├── shared-ts/                     # 共享 TypeScript 代码
│   │   └── src/
│   │       ├── types/                 # 类型定义
│   │       ├── api/                   # API 请求封装
│   │       └── utils/                 # 工具函数
│   └── shared-py/                     # 共享 Python 代码
│       └── src/
│           └── shared_py/
├── scripts/                           # 自动化脚本
├── docs/                              # 项目文档
├── package.json                       # pnpm 根配置
├── pnpm-workspace.yaml                # pnpm 工作区定义
├── pyproject.toml                     # uv / Python 根配置
├── tsconfig.base.json                 # TypeScript 基础配置
└── uv.lock                            # uv 锁文件
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
│  数据分析/模型 │   │  业务API/实时  │
└──────┬───────┘   └──────┬───────┘
       │                  │
       └────────┬─────────┘
                ▼
        ┌──────────────┐
        │  PostgreSQL   │  (规划中)
        │  共享数据库    │
        └──────────────┘
```

- **Python 后端**：负责数据处理、风险模型计算、机器学习推理等计算密集型任务
- **Node 后端**：负责用户认证、业务逻辑、WebSocket 实时通信、前端 BFF 等
- 两者通过 **共享数据库** 和 **内部 API** 协作，互不耦合

## 快速开始

### 环境要求

- **Node.js** ≥ 18
- **pnpm** ≥ 10
- **Python** ≥ 3.12
- **uv** ≥ 0.4

### 安装依赖

```bash
# 安装 Node 依赖（根目录，包含所有 workspace 包）
pnpm install

# 安装 Python 依赖
uv sync
```

### 运行

```bash
# 启动 Python 后端
uv run python apps/server/python-fastapi-backend/src/main.py

# 启动 Node 后端
pnpm --filter node-backend dev

# 启动前端（开发模式）
pnpm --filter web dev
```

## 开发指南

### 添加前端 / Node 依赖

```bash
pnpm --filter <package-name> add <dependency>
```

### 添加 Python 依赖

```bash
# 添加到根项目
uv add <package>

# 添加到子包（进入目录后）
cd packages/shared-py && uv add <package>
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
