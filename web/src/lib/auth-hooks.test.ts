import { describe, expect, it } from "vitest";

import { protectTokens } from "./auth-hooks";
import { decryptToken, parseKey } from "./token-crypto";

const key = parseKey(Buffer.alloc(32, 1).toString("base64"));

describe("protectTokens", () => {
  it("encrypts the refresh token and never stores access or id tokens", () => {
    const out = protectTokens(
      { accountId: "sub-1", refreshToken: "1//refresh", accessToken: "ya29.a", idToken: "eyJ" },
      key,
    );
    expect(out.refreshToken).toMatch(/^v1\./);
    expect(decryptToken(out.refreshToken as string, key)).toBe("1//refresh");
    expect(out.accessToken).toBeNull();
    expect(out.idToken).toBeNull();
    expect(out.accountId).toBe("sub-1");
  });

  it("leaves a partial update without a refresh token alone", () => {
    const out = protectTokens({ scope: "openid" }, key);
    expect(out).toEqual({ scope: "openid" });
  });

  it("does not double-encrypt", () => {
    const once = protectTokens({ refreshToken: "1//r" }, key);
    expect(protectTokens(once, key).refreshToken).toBe(once.refreshToken);
  });
});
