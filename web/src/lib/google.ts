import "server-only";

import { eq } from "drizzle-orm";

import { db } from "@/db";
import { googleConnections } from "@/db/schema";
import { GOOGLE_ADS_SCOPE, GOOGLE_DRIVE_FILE_SCOPE, normalizeScope } from "@/lib/google-scopes";
import { type CustomerClientRow, flattenDiscovery, type RootResult } from "@/lib/discovery";
import { requiredEnv } from "@/lib/env";
import { decryptToken, parseKey } from "@/lib/token-crypto";

/** Must match the Python SDK's version (mcp-server uses v25). */
export const GOOGLE_ADS_API_VERSION = "v25";
const ADS_BASE = `https://googleads.googleapis.com/${GOOGLE_ADS_API_VERSION}`;

export class GoogleGrantRevokedError extends Error {
  constructor() {
    super("Google access was revoked; sign in again");
  }
}

export type Connection = {
  id: string;
  refreshToken: string | null;
  scope: string | null;
  revokedAt: Date | null;
};

export function hasScope(connection: Pick<Connection, "scope">, scope: string): boolean {
  return (connection.scope ?? "").split(/[\s,]+/).includes(scope);
}

export const hasAdsAccess = (c: Connection) =>
  !c.revokedAt && Boolean(c.refreshToken) && hasScope(c, GOOGLE_ADS_SCOPE);
export const hasDriveAccess = (c: Connection) =>
  !c.revokedAt && Boolean(c.refreshToken) && hasScope(c, GOOGLE_DRIVE_FILE_SCOPE);

/**
 * A fresh Google access token from the stored (encrypted) refresh token.
 * `invalid_grant` marks the connection revoked, as the MCP server does.
 *
 * Google reports the scopes actually granted with every token; they are
 * written back to `google_connections.scope` (and to `connection`), because
 * Better Auth does not update `scope` on a repeat sign-in, so a grant that
 * later added Drive would otherwise still look Drive-less.
 */
export async function googleAccessToken(connection: Connection): Promise<string> {
  if (!connection.refreshToken || connection.revokedAt) throw new GoogleGrantRevokedError();
  const refreshToken = decryptToken(connection.refreshToken, parseKey(requiredEnv("TOKEN_ENCRYPTION_KEY")));
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: requiredEnv("GOOGLE_CLIENT_ID"),
      client_secret: requiredEnv("GOOGLE_CLIENT_SECRET"),
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
    cache: "no-store",
  });
  const body = (await res.json().catch(() => ({}))) as {
    access_token?: string;
    scope?: string;
    error?: string;
  };
  if (body.error === "invalid_grant") {
    await db
      .update(googleConnections)
      .set({ revokedAt: new Date() })
      .where(eq(googleConnections.id, connection.id));
    throw new GoogleGrantRevokedError();
  }
  if (!res.ok || !body.access_token) {
    throw new Error(`Google token refresh failed (${res.status} ${body.error ?? ""})`);
  }
  if (body.scope) {
    const granted = normalizeScope(body.scope);
    if (granted !== normalizeScope(connection.scope ?? "")) {
      await db.update(googleConnections).set({ scope: granted }).where(eq(googleConnections.id, connection.id));
    }
    connection.scope = granted;
  }
  return body.access_token;
}

async function adsFetch(path: string, accessToken: string, init: RequestInit & { loginCustomerId?: string } = {}) {
  const headers: Record<string, string> = {
    authorization: `Bearer ${accessToken}`,
    "content-type": "application/json",
  };
  // No developer-token header: retired, the Cloud project carries the access level.
  if (init.loginCustomerId) headers["login-customer-id"] = init.loginCustomerId;
  const res = await fetch(`${ADS_BASE}${path}`, { ...init, headers, cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = (body as { error?: { message?: string } }).error?.message ?? res.statusText;
    throw new Error(`Google Ads ${res.status}: ${message}`);
  }
  return body;
}

const CUSTOMER_CLIENT_QUERY =
  "SELECT customer_client.id, customer_client.descriptive_name, customer_client.manager, " +
  "customer_client.status, customer_client.level FROM customer_client";

async function searchCustomerClients(rootId: string, accessToken: string): Promise<CustomerClientRow[]> {
  const rows: CustomerClientRow[] = [];
  let pageToken: string | undefined;
  do {
    const page = (await adsFetch(`/customers/${rootId}/googleAds:search`, accessToken, {
      method: "POST",
      loginCustomerId: rootId,
      body: JSON.stringify({ query: CUSTOMER_CLIENT_QUERY, ...(pageToken ? { pageToken } : {}) }),
    })) as { results?: CustomerClientRow[]; nextPageToken?: string };
    rows.push(...(page.results ?? []));
    pageToken = page.nextPageToken;
  } while (pageToken);
  return rows;
}

/**
 * Every enabled, non-manager account the grant reaches: the accessible
 * customers, then a customer_client walk under each (spec account-connection).
 */
export async function discoverAccounts(connection: Connection) {
  const accessToken = await googleAccessToken(connection);
  const { resourceNames = [] } = (await adsFetch("/customers:listAccessibleCustomers", accessToken)) as {
    resourceNames?: string[];
  };
  const rootIds = resourceNames.map((name) => name.replace("customers/", ""));
  const results: RootResult[] = await Promise.all(
    rootIds.map(async (rootId) => {
      try {
        return { rootId, rows: await searchCustomerClients(rootId, accessToken) };
      } catch (error) {
        return { rootId, error: error instanceof Error ? error.message : String(error) };
      }
    }),
  );
  return flattenDiscovery(results);
}
