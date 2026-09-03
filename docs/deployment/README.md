# 部署指南

## Docker 部署（推荐）

```bash
cd infra/docker
docker compose up -d
```

详见 [infra/README.md](../../infra/README.md)。

## 手动部署

### 数据库

```bash
# 启动 PostgreSQL（需安装 PostGIS + pgvector 扩展）
psql -U postgres -f infra/db/init.sql
```

### Python 后端

```bash
cd apps/server/python-fastapi-backend
uv sync
alembic upgrade head
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Node 后端

```bash
pnpm install
pnpm --filter @st-risk/node-backend build
pnpm --filter @st-risk/node-backend start:prod
```

### 前端

```bash
pnpm --filter @st-risk/web-frontend build
# 将 dist/ 部署到 Nginx 或静态文件服务器
```

## 环境变量

| 服务 | 变量 | 说明 |
|------|------|------|
| Python | `UAV_DATABASE_URL` | PostgreSQL 连接（asyncpg） |
| Node | `DATABASE_URL` | PostgreSQL 连接 |
| Node | `PYTHON_BACKEND_URL` | Python 后端地址 |
| Node | `PORT` | 服务端口（默认 3000） |
