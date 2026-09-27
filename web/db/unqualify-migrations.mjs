// drizzle-kit writes `"public".` into foreign keys and views even for
// unqualified tables. Our migrations must stay schema-agnostic: they run
// once per environment as a role whose search_path is `app` or `app_dev`
// (ROADMAP D11). Run after every `drizzle-kit generate` (npm run db:generate).
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const dir = new URL("./migrations/", import.meta.url).pathname;
for (const file of readdirSync(dir).filter((f) => f.endsWith(".sql"))) {
  const path = join(dir, file);
  const sql = readFileSync(path, "utf8");
  const fixed = sql.replaceAll('"public".', "");
  if (fixed !== sql) {
    writeFileSync(path, fixed);
    console.log(`unqualified ${file}`);
  }
}
