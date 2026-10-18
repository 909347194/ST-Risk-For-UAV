// drizzle-kit 配置 — 用于 `pnpm db:generate` / `pnpm db:migrate`
// 生成迁移不需要连接数据库（仅读取 schema 与迁移 journal 做 diff）。

import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  schema: './src/db/models/index.ts',
  out: './drizzle',
  dialect: 'postgresql',
  dbCredentials: {
    url:
      process.env.DATABASE_URL ?? 'postgresql://postgres:postgres@localhost:5432/st_risk',
  },
});
