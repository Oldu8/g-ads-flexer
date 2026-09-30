import "server-only";

import { and, type AnyColumn, desc, eq, inArray, isNull, sql } from "drizzle-orm";

import { db } from "@/db";
import {
  adAccounts,
  googleConnections,
  oauthClients,
  oauthConsents,
  oauthRefreshTokens,
  oauthResources,
} from "@/db/schema";
import type { OfferedAccount } from "@/lib/discovery";
import { requiredEnv } from "@/lib/env";
import { createFixesSheet, fixesSheetTitle, probeFixesSheet, type SheetState } from "@/lib/fixes-sheet";
import { formatCustomerId } from "@/lib/format";
import { type Connection, googleAccessToken, hasDriveAccess } from "@/lib/google";
import { mcpUrl, newMcpSlug } from "@/lib/mcp-url";

/**
 * Every query here is scoped by the signed-in user's id (spec
 * account-connection, "Users only see their own rows"); callers pass the
 * session user, never an id taken from a form alone.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const CONTEXT_MAX = 2000;

export function accountMcpUrl(slug: string): string {
  return mcpUrl(requiredEnv("MCP_PUBLIC_URL"), slug);
}

export async function getConnection(userId: string): Promise<Connection | undefined> {
  const [row] = await db
    .select({
      id: googleConnections.id,
      refreshToken: googleConnections.refreshToken,
      scope: googleConnections.scope,
      revokedAt: googleConnections.revokedAt,
    })
    .from(googleConnections)
    .where(and(eq(googleConnections.userId, userId), eq(googleConnections.providerId, "google")))
    .limit(1);
  return row;
}

export async function listAccounts(userId: string) {
  return db
    .select()
    .from(adAccounts)
    .where(eq(adAccounts.userId, userId))
    .orderBy(adAccounts.displayName, adAccounts.customerId);
}

export type Account = Awaited<ReturnType<typeof listAccounts>>[number];

/** The user's account with this id, or undefined (also for malformed ids). */
export async function getAccount(userId: string, id: string): Promise<Account | undefined> {
  if (!UUID.test(id)) return undefined;
  const [row] = await db
    .select()
    .from(adAccounts)
    .where(and(eq(adAccounts.id, id), eq(adAccounts.userId, userId)))
    .limit(1);
  return row;
}

/**
 * Creates rows for newly chosen accounts: the account with its MCP slug,
 * the OAuth resource for its URL, then its fixes-log sheet (best-effort).
 * Existing accounts are left alone; nothing is deleted.
 */
export async function addAccounts(userId: string, connection: Connection, chosen: OfferedAccount[]) {
  const existing = new Set(
    (
      await db
        .select({ customerId: adAccounts.customerId })
        .from(adAccounts)
        .where(eq(adAccounts.googleConnectionId, connection.id))
    ).map((r) => r.customerId),
  );
  const created: Account[] = [];
  for (const offered of chosen) {
    if (existing.has(offered.customerId)) continue;
    const slug = newMcpSlug();
    const account = await db.transaction(async (tx) => {
      const [row] = await tx
        .insert(adAccounts)
        .values({
          userId,
          googleConnectionId: connection.id,
          customerId: offered.customerId,
          loginCustomerId: offered.loginCustomerId,
          displayName: offered.displayName,
          mcpSlug: slug,
        })
        .returning();
      await tx.insert(oauthResources).values({
        identifier: accountMcpUrl(slug),
        name: `${offered.displayName || "Google Ads"} (${formatCustomerId(offered.customerId)})`,
        createdAt: new Date(),
        updatedAt: new Date(),
      });
      return row;
    });
    created.push(account);
  }
  for (const account of created) {
    await createSheetFor(account, connection).catch(() => undefined);
  }
  return created.length;
}

/** Creates (or replaces) the account's sheet; false when Drive is not granted. */
export async function createSheetFor(account: Account, connection: Connection): Promise<boolean> {
  // Minting first refreshes connection.scope from what Google reports.
  const token = await googleAccessToken(connection);
  if (!hasDriveAccess(connection)) return false;
  const id = await createFixesSheet(token, fixesSheetTitle(account.displayName, account.customerId));
  await db.update(adAccounts).set({ fixesSheetId: id }).where(eq(adAccounts.id, account.id));
  return true;
}

export type SheetStatus = SheetState | "none" | "no_access" | "unknown";

export async function sheetStatus(account: Account, connection: Connection | undefined): Promise<SheetStatus> {
  if (!connection) return "no_access";
  let token: string;
  try {
    // Also refreshes connection.scope from what Google reports.
    token = await googleAccessToken(connection);
  } catch {
    return hasDriveAccess(connection) ? "unknown" : "no_access";
  }
  if (!hasDriveAccess(connection)) return "no_access";
  if (!account.fixesSheetId) return "none";
  try {
    return await probeFixesSheet(token, account.fixesSheetId);
  } catch {
    return "unknown";
  }
}

export async function setEnabled(userId: string, id: string, enabled: boolean) {
  const account = await getAccount(userId, id);
  if (!account) return false;
  await db.transaction(async (tx) => {
    await tx.update(adAccounts).set({ enabled }).where(eq(adAccounts.id, account.id));
    // A disabled resource is refused at /oauth2/authorize as well.
    await tx
      .update(oauthResources)
      .set({ disabled: !enabled, updatedAt: new Date() })
      .where(eq(oauthResources.identifier, accountMcpUrl(account.mcpSlug)));
  });
  return true;
}

export async function setAllowChanges(userId: string, id: string, allow: boolean) {
  const account = await getAccount(userId, id);
  if (!account) return false;
  await db
    .update(adAccounts)
    .set({ toolProfile: allow ? "manager" : "read_only" })
    .where(eq(adAccounts.id, account.id));
  return true;
}

export async function setContext(userId: string, id: string, context: string) {
  if (context.length > CONTEXT_MAX) return false;
  const account = await getAccount(userId, id);
  if (!account) return false;
  await db.update(adAccounts).set({ context }).where(eq(adAccounts.id, account.id));
  return true;
}

const containsResource = (column: AnyColumn, url: string) =>
  sql`${column} @> ARRAY[${url}]::text[]`;

/** MCP clients the user approved for this account, newest first. */
export async function listConnectedClients(userId: string, account: Account) {
  const url = accountMcpUrl(account.mcpSlug);
  const consents = await db
    .select({
      clientId: oauthConsents.clientId,
      name: oauthClients.name,
      connectedAt: oauthConsents.createdAt,
      updatedAt: oauthConsents.updatedAt,
    })
    .from(oauthConsents)
    .innerJoin(oauthClients, eq(oauthClients.clientId, oauthConsents.clientId))
    .where(and(eq(oauthConsents.userId, userId), containsResource(oauthConsents.resources, url)))
    .orderBy(desc(oauthConsents.updatedAt));
  if (consents.length === 0) return [];
  const refreshed = await db
    .select({
      clientId: oauthRefreshTokens.clientId,
      last: sql<string | Date | null>`max(${oauthRefreshTokens.createdAt})`,
    })
    .from(oauthRefreshTokens)
    .where(
      and(
        eq(oauthRefreshTokens.userId, userId),
        inArray(
          oauthRefreshTokens.clientId,
          consents.map((c) => c.clientId),
        ),
        containsResource(oauthRefreshTokens.resources, url),
      ),
    )
    .groupBy(oauthRefreshTokens.clientId);
  const lastByClient = new Map(refreshed.map((r) => [r.clientId, r.last]));
  return consents.map((c) => ({ ...c, lastRefreshedAt: lastByClient.get(c.clientId) ?? null }));
}

/** Revokes one client's consent and refresh tokens for one account URL. */
async function revokeClients(userId: string, url: string, clientId?: string) {
  const byClient = (column: AnyColumn) => (clientId ? [eq(column, clientId)] : []);
  await db.transaction(async (tx) => {
    await tx
      .delete(oauthConsents)
      .where(
        and(
          eq(oauthConsents.userId, userId),
          containsResource(oauthConsents.resources, url),
          ...byClient(oauthConsents.clientId),
        ),
      );
    await tx
      .update(oauthRefreshTokens)
      .set({ revoked: new Date() })
      .where(
        and(
          eq(oauthRefreshTokens.userId, userId),
          isNull(oauthRefreshTokens.revoked),
          containsResource(oauthRefreshTokens.resources, url),
          ...byClient(oauthRefreshTokens.clientId),
        ),
      );
  });
}

export async function disconnectClient(userId: string, id: string, clientId: string) {
  const account = await getAccount(userId, id);
  if (!account) return false;
  await revokeClients(userId, accountMcpUrl(account.mcpSlug), clientId);
  return true;
}

/**
 * Removes the account: every client loses access, the OAuth resource goes,
 * and the row (with its queue and usage) is deleted. The sheet stays in the
 * user's Drive.
 */
export async function removeAccount(userId: string, id: string) {
  const account = await getAccount(userId, id);
  if (!account) return false;
  const url = accountMcpUrl(account.mcpSlug);
  await revokeClients(userId, url);
  await db.transaction(async (tx) => {
    await tx.delete(oauthResources).where(eq(oauthResources.identifier, url));
    await tx.delete(adAccounts).where(and(eq(adAccounts.id, account.id), eq(adAccounts.userId, userId)));
  });
  return true;
}
