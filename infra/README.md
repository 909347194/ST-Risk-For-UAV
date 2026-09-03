# 基础设施

## 目录结构

```
infra/
├── docker/
│   ├── Dockerfile.python        # Python 后端镜像
│   ├── Dockerfile.node          # Node 后端镜像
│   ├── Dockerfile.frontend      # 前端镜像（Nginx）
│   └── docker-compose.yml       # 一键启动全部服务
├── db/
│   ├── init.sql                 # PostgreSQL 初始化（PostGIS + pgvector）
│   └── migrations/              # 数据库迁移脚本
└── nginx/
    └── nginx.conf               # 反向代理配置
```

## 一键启动

```bash
cd infra/docker
docker compose up -d
```

启动后访问：
- 前端：http://localhost
- Node 后端：http://localhost:3000
- Python 后端：http://localhost:8000
- PostgreSQL：localhost:5432

## 单独启动

```bash
# 只启动数据库
docker compose up postgres -d

# 只启动 Python 后端
docker compose up python-backend -d

# 只启动 Node 后端
docker compose up node-backend -d
```

## 数据库

### 初始化

`init.sql` 会在 PostgreSQL 首次启动时自动执行，启用：
- PostGIS（空间数据）
- pgvector（向量搜索）

### 迁移

```bash
# Python（Alembic）
cd apps/server/python-fastapi-backend
alembic revision --autogenerate -m "描述"
alembic upgrade head

# Node（Drizzle Kit）
cd apps/server/node-backend
pnpm db:generate
pnpm db:migrate
```
