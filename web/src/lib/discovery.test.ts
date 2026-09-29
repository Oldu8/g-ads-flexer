import { describe, expect, it } from "vitest";

import { flattenDiscovery, type RootResult } from "@/lib/discovery";

// Shapes as returned by POST /v25/customers/{id}/googleAds:search on
// customer_client (int64 ids and levels come back as strings).
const row = (id: string, name: string, manager: boolean, level: number, status = "ENABLED") => ({
  customerClient: {
    resourceName: `customers/x/customerClients/${id}`,
    id,
    descriptiveName: name,
    manager,
    status,
    level: String(level),
  },
});

describe("flattenDiscovery", () => {
  it("offers a directly accessible account with no login customer id", () => {
    const result = flattenDiscovery([{ rootId: "3333333333", rows: [row("3333333333", "Shop", false, 0)] }]);
    expect(result.accounts).toEqual([
      { customerId: "3333333333", loginCustomerId: null, displayName: "Shop", level: 0 },
    ]);
  });

  it("offers children of a manager through that manager, not the manager itself", () => {
    const result = flattenDiscovery([
      {
        rootId: "1111111111",
        rows: [row("1111111111", "Agency MCC", true, 0), row("2222222222", "Client A", false, 1)],
      },
    ]);
    expect(result.accounts).toEqual([
      { customerId: "2222222222", loginCustomerId: "1111111111", displayName: "Client A", level: 1 },
    ]);
    expect(result.managers).toEqual({ "1111111111": "Agency MCC" });
  });

  it("walks nested managers from the top manager", () => {
    const result = flattenDiscovery([
      {
        rootId: "1111111111",
        rows: [
          row("1111111111", "Top", true, 0),
          row("4444444444", "Sub MCC", true, 1),
          row("5555555555", "Deep client", false, 2),
        ],
      },
    ]);
    expect(result.accounts.map((a) => [a.customerId, a.loginCustomerId, a.level])).toEqual([
      ["5555555555", "1111111111", 2],
    ]);
  });

  it("skips disabled and cancelled accounts", () => {
    const result = flattenDiscovery([
      {
        rootId: "1111111111",
        rows: [
          row("1111111111", "MCC", true, 0),
          row("6666666666", "Old", false, 1, "CANCELED"),
          row("7777777777", "Paused?", false, 1, "SUSPENDED"),
        ],
      },
    ]);
    expect(result.accounts).toEqual([]);
    expect(result.managers).toEqual({});
  });

  it("offers an account reached twice once, direct access first", () => {
    const results: RootResult[] = [
      { rootId: "1111111111", rows: [row("1111111111", "MCC", true, 0), row("4444444444", "Both", false, 1)] },
      { rootId: "4444444444", rows: [row("4444444444", "Both", false, 0)] },
    ];
    for (const order of [results, [...results].reverse()]) {
      const { accounts } = flattenDiscovery(order);
      expect(accounts).toEqual([
        { customerId: "4444444444", loginCustomerId: null, displayName: "Both", level: 0 },
      ]);
    }
  });

  it("prefers the nearest manager when there is no direct access", () => {
    const { accounts } = flattenDiscovery([
      { rootId: "1111111111", rows: [row("1111111111", "Top", true, 0), row("8888888888", "C", false, 2)] },
      { rootId: "9999999999", rows: [row("9999999999", "Near", true, 0), row("8888888888", "C", false, 1)] },
    ]);
    expect(accounts[0].loginCustomerId).toBe("9999999999");
  });

  it("reports roots whose search failed", () => {
    const result = flattenDiscovery([{ rootId: "1234567890", error: "CUSTOMER_NOT_ENABLED" }]);
    expect(result).toEqual({ accounts: [], managers: {}, failedRoots: ["1234567890"] });
  });
});
