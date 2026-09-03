-- PostgreSQL 初始化脚本 — 启用 PostGIS + pgvector 扩展

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS vector;
