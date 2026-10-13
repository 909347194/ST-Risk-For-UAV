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
