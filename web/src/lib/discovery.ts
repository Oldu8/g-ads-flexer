/**
 * Flattening Google Ads discovery results into the accounts a user can
 * expose (spec account-connection, "Discovery lists every reachable ad
 * account"). Pure, so it is tested with recorded API responses.
 */

/** One `customer_client` row as returned by the REST search API. */
export type CustomerClientRow = {
  customerClient: {
    id?: string;
    descriptiveName?: string;
    manager?: boolean;
    status?: string;
    level?: string | number;
  };
};

/** The customer_client search run with login-customer-id = `rootId`. */
export type RootResult = { rootId: string; rows: CustomerClientRow[] } | { rootId: string; error: string };

export type OfferedAccount = {
  customerId: string;
  /** null = the grant reaches the account directly. */
  loginCustomerId: string | null;
  displayName: string;
  level: number;
};

export type DiscoveryResult = {
  accounts: OfferedAccount[];
  /** Names of the managers that reach at least one offered account. */
  managers: Record<string, string>;
  /** Roots whose search failed (e.g. a cancelled account). */
  failedRoots: string[];
};

/**
 * Only enabled, non-manager accounts are offered. An account reached several
 * ways is offered once: direct access wins, then the lowest level, then the
 * first root seen.
 */
export function flattenDiscovery(results: RootResult[]): DiscoveryResult {
  const best = new Map<string, OfferedAccount>();
  const managerNames: Record<string, string> = {};
  const failedRoots: string[] = [];

  for (const result of results) {
    if ("error" in result) {
      failedRoots.push(result.rootId);
      continue;
    }
    for (const { customerClient: c } of result.rows) {
      if (!c.id) continue;
      const level = Number(c.level ?? 0);
      const name = c.descriptiveName ?? "";
      if (c.id === result.rootId && c.manager) managerNames[c.id] = name;
      if (c.manager || c.status !== "ENABLED") continue;
      const candidate: OfferedAccount = {
        customerId: c.id,
        loginCustomerId: c.id === result.rootId ? null : result.rootId,
        displayName: name,
        level: c.id === result.rootId ? 0 : level,
      };
      const current = best.get(c.id);
      if (!current || rank(candidate) < rank(current)) best.set(c.id, candidate);
    }
  }

  const accounts = [...best.values()].sort(
    (a, b) => a.displayName.localeCompare(b.displayName) || a.customerId.localeCompare(b.customerId),
  );
  const managers: Record<string, string> = {};
  for (const a of accounts) {
    if (a.loginCustomerId) managers[a.loginCustomerId] = managerNames[a.loginCustomerId] ?? "";
  }
  return { accounts, managers, failedRoots };
}

function rank(a: OfferedAccount): number {
  return a.loginCustomerId === null ? -1 : a.level;
}
