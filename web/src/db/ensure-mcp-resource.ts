import postgres from "postgres";

/**
 * Makes sure the canonical MCP resource row exists before the first request.
 *
 * `@better-auth/mcp` seeds it during auth init, and on a cold start several
 * route bundles init auth at once; the losers hit the unique constraint, and
 * Better Auth only recognises that error by its message, which Drizzle wraps
 * ("Failed query: …"). The failed init is cached and every auth request
 * answers 500 until a restart. With the row already present, init only reads.
 */
export async function ensureMcpResource(): Promise<void> {
  const url = process.env.DATABASE_URL;
  const resource = process.env.MCP_PUBLIC_URL;
  if (!url || !resource) return;
  const sql = postgres(url, { max: 1 });
  try {
    await sql`
      insert into oauth_resources (identifier, name, disabled, dpop_bound_access_tokens_required,
                                   policy_version, created_at, updated_at)
      values (${resource}, ${resource}, false, false, 1, now(), now())
      on conflict (identifier) do nothing`;
  } catch (error) {
    // Not migrated yet: Better Auth defers seeding to first use.
    console.warn("ensureMcpResource skipped:", error instanceof Error ? error.message : error);
  } finally {
    await sql.end();
  }
}
