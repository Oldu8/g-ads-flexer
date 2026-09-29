/** Runs once per server process, before it handles requests. */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { ensureMcpResource } = await import("./db/ensure-mcp-resource");
  await ensureMcpResource();
}
