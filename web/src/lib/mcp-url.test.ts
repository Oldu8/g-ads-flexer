import { describe, expect, it } from "vitest";

import { MCP_SLUG_PATTERN, mcpUrl, newMcpSlug, slugFromMcpUrl } from "@/lib/mcp-url";

const BASE = "https://ads-mcp.vtrata.com/mcp";

describe("mcp urls", () => {
  it("makes 12-char [a-z0-9] slugs that differ", () => {
    const slugs = new Set(Array.from({ length: 200 }, newMcpSlug));
    expect(slugs.size).toBe(200);
    for (const slug of slugs) expect(slug).toMatch(MCP_SLUG_PATTERN);
  });

  it("round-trips a slug through the account url", () => {
    expect(mcpUrl(`${BASE}/`, "k7d2m9x4q1ta")).toBe(`${BASE}/k7d2m9x4q1ta`);
    expect(slugFromMcpUrl(BASE, `${BASE}/k7d2m9x4q1ta`)).toBe("k7d2m9x4q1ta");
  });

  it("rejects anything that is not an account url", () => {
    expect(slugFromMcpUrl(BASE, BASE)).toBeNull();
    expect(slugFromMcpUrl(BASE, `${BASE}/k7d2m9x4q1ta/extra`)).toBeNull();
    expect(slugFromMcpUrl(BASE, "https://evil.example/mcp/k7d2m9x4q1ta")).toBeNull();
    expect(slugFromMcpUrl(BASE, `${BASE}/K7D2M9X4Q1TA`)).toBeNull();
  });
});
