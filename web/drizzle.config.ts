import { defineConfig } from "drizzle-kit";

/**
 * Migrations run as the schema-owning web role of each environment
 * (`web_dev` -> app_dev, `web_prod` -> app); tables are unqualified and land
 * in that role's search_path schema. The journal table lives in the same
 * schema (DB_SCHEMA), so dev and prod keep separate migration histories.
 */
export default defineConfig({
  dialect: "postgresql",
  schema: "./src/db/schema.ts",
  out: "./db/migrations",
  dbCredentials: { url: process.env.DATABASE_URL ?? "" },
  migrations: { schema: process.env.DB_SCHEMA ?? "app_dev", table: "__drizzle_migrations" },
  strict: true,
  verbose: true,
});
