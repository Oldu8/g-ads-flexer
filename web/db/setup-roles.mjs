// Create the schemas and roles of ROADMAP D11 in the Supabase project:
//
//   dev:  schema app_dev, owner web_dev, mcp role mcp_dev
//   prod: schema app,     owner web_prod, mcp role mcp_prod
//
// Each role's search_path points at its schema, so unqualified migrations
// and queries land in the right place, and dev roles cannot read prod.
// MCP roles are NOLOGIN here; Phase C gives them a password and table grants.
//
// Usage (from web/, ADMIN_DATABASE_URL in .env.local = the Supabase *Session
// pooler* connection string of the `postgres` user):
//   npm run db:setup-roles                 # both environments
//   npm run db:setup-roles -- --env=dev    # one environment
//   npm run db:setup-roles -- --rotate     # new passwords for existing web roles
//
// Generated passwords are never printed: dev credentials go into .env.local,
// prod credentials into the Railway `web` service variables.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

import postgres from "postgres";

const ENVIRONMENTS = {
  dev: { schema: "app_dev", web: "web_dev", mcp: "mcp_dev" },
  prod: { schema: "app", web: "web_prod", mcp: "mcp_prod" },
};
const ENV_FILE = ".env.local";

const adminUrl = process.env.ADMIN_DATABASE_URL;
if (!adminUrl) {
  console.error("ADMIN_DATABASE_URL is not set in .env.local");
  process.exit(1);
}
const parsed = new URL(adminUrl);
const projectRef = decodeURIComponent(parsed.username).split(".")[1];
if (!projectRef) {
  console.error(
    "ADMIN_DATABASE_URL must be the Session pooler string (user postgres.<project-ref>)",
  );
  process.exit(1);
}
const database = parsed.pathname.replace(/^\//, "") || "postgres";

const args = process.argv.slice(2);
const only = args.find((a) => a.startsWith("--env="))?.split("=")[1] ?? "all";
const rotate = args.includes("--rotate");

const sql = postgres(adminUrl, { max: 1, onnotice: () => {} });
const newPassword = () => randomBytes(24).toString("base64url");
const roleExists = async (name) =>
  (await sql`select 1 from pg_roles where rolname = ${name}`).length > 0;

function roleUrl(role, password) {
  const url = new URL(adminUrl);
  url.username = `${role}.${projectRef}`;
  url.password = password;
  return url.toString();
}

function upsertEnvFile(values) {
  let text = existsSync(ENV_FILE) ? readFileSync(ENV_FILE, "utf8") : "";
  for (const [key, value] of Object.entries(values)) {
    const line = `${key}=${value}`;
    const pattern = new RegExp(`^${key}=.*$`, "m");
    text = pattern.test(text)
      ? text.replace(pattern, line)
      : `${text}${text && !text.endsWith("\n") ? "\n" : ""}${line}\n`;
  }
  writeFileSync(ENV_FILE, text);
}

function setRailwayVariables(values) {
  const setArgs = Object.entries(values).flatMap(([k, v]) => ["--set", `${k}=${v}`]);
  const result = spawnSync(
    "railway",
    ["variables", "--service", "web", "--skip-deploys", ...setArgs],
    { stdio: ["ignore", "ignore", "inherit"] },
  );
  if (result.status !== 0) throw new Error("railway variables --set failed");
}

try {
  for (const [name, env] of Object.entries(ENVIRONMENTS)) {
    if (only !== "all" && only !== name) continue;
    const { schema, web, mcp } = env;

    let webPassword = null;
    if (!(await roleExists(web))) {
      webPassword = newPassword();
      await sql.unsafe(`CREATE ROLE ${web} LOGIN PASSWORD '${webPassword}'`);
    } else if (rotate) {
      webPassword = newPassword();
      await sql.unsafe(`ALTER ROLE ${web} PASSWORD '${webPassword}'`);
    }
    if (!(await roleExists(mcp))) await sql.unsafe(`CREATE ROLE ${mcp} NOLOGIN`);

    // The admin must be a member of the web role to hand it the schema.
    await sql.unsafe(`GRANT ${web} TO CURRENT_USER`);
    await sql.unsafe(`CREATE SCHEMA IF NOT EXISTS ${schema} AUTHORIZATION ${web}`);
    await sql.unsafe(`ALTER SCHEMA ${schema} OWNER TO ${web}`);
    await sql.unsafe(`REVOKE ALL ON SCHEMA ${schema} FROM PUBLIC`);
    await sql.unsafe(`GRANT USAGE ON SCHEMA ${schema} TO ${mcp}`);
    await sql.unsafe(`ALTER ROLE ${web} SET search_path = ${schema}`);
    await sql.unsafe(`ALTER ROLE ${mcp} SET search_path = ${schema}`);
    // drizzle-kit migrate issues CREATE SCHEMA IF NOT EXISTS for its journal,
    // which Postgres checks against CREATE on the database.
    await sql.unsafe(`GRANT CREATE ON DATABASE ${database} TO ${web}`);

    if (webPassword) {
      const values = { DATABASE_URL: roleUrl(web, webPassword), DB_SCHEMA: schema };
      if (name === "dev") {
        upsertEnvFile(values);
        console.log(`${name}: ${web} ready; credentials written to ${ENV_FILE}`);
      } else {
        setRailwayVariables(values);
        console.log(`${name}: ${web} ready; credentials set on Railway service "web"`);
      }
    } else {
      console.log(`${name}: ${web} already existed; schema and grants re-applied`);
    }
  }
} finally {
  await sql.end();
}
