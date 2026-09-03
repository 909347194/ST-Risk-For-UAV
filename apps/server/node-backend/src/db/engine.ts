// Drizzle ORM — 异步引擎 + 数据库实例

import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import * as schema from './models';

const DB_PATH = process.env.UAV_DATABASE_URL || './data/uav.db';

const sqlite = new Database(DB_PATH);
export const db = drizzle(sqlite, { schema });
