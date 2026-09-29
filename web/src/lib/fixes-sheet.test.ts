import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import {
  createFixesSheet,
  FIXES_HEADER,
  FIXES_WORKSHEET,
  fixesSheetTitle,
  probeFixesSheet,
  spreadsheetBody,
} from "@/lib/fixes-sheet";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("fixes-log sheet", () => {
  it("titles the sheet after the account", () => {
    expect(fixesSheetTitle("Shop", "1234567890")).toBe("Adsmigo fixes log — Shop (123-456-7890)");
    expect(fixesSheetTitle(" ", "1234567890")).toBe("Adsmigo fixes log — Google Ads (123-456-7890)");
  });

  it("creates one frozen tab with the contract header", () => {
    const body = spreadsheetBody("t");
    const [tab] = body.sheets;
    expect(tab.properties.title).toBe(FIXES_WORKSHEET);
    expect(tab.properties.gridProperties.frozenRowCount).toBe(1);
    expect(tab.data[0].rowData[0].values.map((v) => v.userEnteredValue.stringValue)).toEqual(FIXES_HEADER);
  });

  it("returns the new spreadsheet id", async () => {
    const fetchImpl = vi.fn(async () => json(200, { spreadsheetId: "abc" }));
    await expect(createFixesSheet("tok", "t", fetchImpl)).resolves.toBe("abc");
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://sheets.googleapis.com/v4/spreadsheets");
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer tok");
  });

  it("fails loudly when Google refuses", async () => {
    await expect(createFixesSheet("tok", "t", async () => json(403, {}))).rejects.toThrow("403");
  });

  it.each([
    [json(200, { id: "abc", trashed: false }), "ok"],
    [json(200, { id: "abc", trashed: true }), "missing"],
    [json(404, {}), "missing"],
    [json(403, {}), "missing"],
  ])("probes the sheet state", async (response, state) => {
    await expect(probeFixesSheet("tok", "abc", async () => response)).resolves.toBe(state);
  });

  it("does not call a Google outage a missing sheet", async () => {
    await expect(probeFixesSheet("tok", "abc", async () => json(500, {}))).rejects.toThrow("500");
  });

  // Contract with the MCP server (spec platform-schema, "Fixes-log header
  // contract"): until Phase C makes Python read the JSON, its hardcoded
  // HEADER must match.
  it("matches the MCP server's fixes-log header", () => {
    const python = readFileSync(
      new URL("../../../mcp-server/src/services/review/fixes_log_sheet.py", import.meta.url),
      "utf8",
    );
    const block = python.match(/^HEADER: List\[str\] = \[([\s\S]*?)\]/m)?.[1] ?? "";
    const columns = [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    expect(columns).toEqual(FIXES_HEADER);
    expect(python).toContain(`DEFAULT_WORKSHEET_NAME = "${FIXES_WORKSHEET}"`);
  });
});
