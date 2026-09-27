import "server-only";

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

import { requiredEnv } from "@/lib/env";

import * as schema from "./schema";

/**
 * One pooled client per server process. DATABASE_URL uses the environment's
 * web role (web_dev / web_prod) through the Supabase session pooler; the
 * role's search_path selects the schema (app_dev / app).
 */
const globalForDb = globalThis as unknown as { pg?: ReturnType<typeof postgres> };

const client = globalForDb.pg ?? postgres(requiredEnv("DATABASE_URL"), { max: 5 });
if (process.env.NODE_ENV !== "production") globalForDb.pg = client;

export const db = drizzle(client, { schema });
