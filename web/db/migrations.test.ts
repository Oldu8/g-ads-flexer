import { readdirSync, readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// Migrations run once per environment under a role whose search_path picks
// the schema (app / app_dev); a hard-coded schema would break that.
describe("migrations", () => {
  const dir = new URL("./migrations/", import.meta.url);
  const files = readdirSync(dir).filter((f) => f.endsWith(".sql"));

  it("exist", () => expect(files.length).toBeGreaterThan(0));

  it.each(files)("%s is schema-agnostic (run npm run db:generate)", (file) => {
    const sql = readFileSync(new URL(file, dir), "utf8");
    expect(sql).not.toMatch(/"(public|app|app_dev)"\./);
  });
});
