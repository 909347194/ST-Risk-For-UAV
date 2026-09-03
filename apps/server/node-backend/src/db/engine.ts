// Drizzle ORM — PostgreSQL + PostGIS + pgvector

import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './models';

const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/st_risk';

const client = postgres(DATABASE_URL);
export const db = drizzle(client, { schema });
