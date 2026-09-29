import "server-only";

import { and, eq, inArray, isNull } from "drizzle-orm";

import { db } from "@/db";
import { adAccounts, googleConnections } from "@/db/schema";
import { requiredEnv } from "@/lib/env";
import { slugFromMcpUrl } from "@/lib/mcp-url";

export type ResourceCheck =
  | { ok: true; accounts: { id: string; displayName: string; customerId: string; toolProfile: string }[] }
  | { ok: false; reason: "not_an_account" | "not_yours_or_disabled" };

/**
 * May `userId` get a token for these OAuth resources? Every resource must
 * be the MCP URL of one of the user's enabled accounts whose Google grant
 * is not revoked (spec account-connection, "MCP clients get access through
 * OAuth"). Used before consent and at every token issuance.
 */
export async function checkMcpResources(
  userId: string | undefined,
  resources: readonly string[] | undefined,
): Promise<ResourceCheck> {
  const base = requiredEnv("MCP_PUBLIC_URL");
  const slugs = (resources ?? []).map((r) => slugFromMcpUrl(base, r));
  if (!userId || slugs.length === 0 || slugs.some((s) => s === null)) {
    return { ok: false, reason: "not_an_account" };
  }
  const rows = await db
    .select({
      id: adAccounts.id,
      displayName: adAccounts.displayName,
      customerId: adAccounts.customerId,
      toolProfile: adAccounts.toolProfile,
    })
    .from(adAccounts)
    .innerJoin(googleConnections, eq(googleConnections.id, adAccounts.googleConnectionId))
    .where(
      and(
        inArray(adAccounts.mcpSlug, slugs as string[]),
        eq(adAccounts.userId, userId),
        eq(adAccounts.enabled, true),
        isNull(googleConnections.revokedAt),
      ),
    );
  if (rows.length !== new Set(slugs).size) return { ok: false, reason: "not_yours_or_disabled" };
  return { ok: true, accounts: rows };
}
