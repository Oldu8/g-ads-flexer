import { describe, expect, it } from "vitest";

import { GOOGLE_ADS_SCOPE, GOOGLE_DRIVE_FILE_SCOPE, normalizeScope } from "@/lib/google-scopes";

describe("normalizeScope", () => {
  it("turns Google's space-separated scope into Better Auth's comma list", () => {
    expect(normalizeScope(`openid ${GOOGLE_DRIVE_FILE_SCOPE} ${GOOGLE_ADS_SCOPE}`)).toBe(
      [GOOGLE_ADS_SCOPE, GOOGLE_DRIVE_FILE_SCOPE, "openid"].join(","),
    );
  });

  it("compares a stored comma list and a Google answer as equal", () => {
    expect(normalizeScope(`openid,${GOOGLE_ADS_SCOPE}`)).toBe(normalizeScope(`${GOOGLE_ADS_SCOPE} openid`));
    expect(normalizeScope("")).toBe("");
  });
});
