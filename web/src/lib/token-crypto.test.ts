import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { decryptToken, encryptToken, parseKey, TOKEN_AAD } from "./token-crypto";

const vector = JSON.parse(
  readFileSync(new URL("../../db/test-vectors/token-encryption.json", import.meta.url), "utf8"),
) as { key_base64: string; nonce_hex: string; aad: string; plaintext: string; expected: string };

describe("token encryption (shared with the Python MCP server)", () => {
  const key = parseKey(vector.key_base64);

  it("reproduces the committed test vector", () => {
    expect(TOKEN_AAD).toBe(vector.aad);
    expect(encryptToken(vector.plaintext, key, Buffer.from(vector.nonce_hex, "hex"))).toBe(
      vector.expected,
    );
    expect(decryptToken(vector.expected, key)).toBe(vector.plaintext);
  });

  it("uses a fresh nonce each time", () => {
    expect(encryptToken("same", key)).not.toBe(encryptToken("same", key));
  });

  it("rejects a wrong key and tampered ciphertext", () => {
    const other = parseKey(Buffer.alloc(32, 7).toString("base64"));
    expect(() => decryptToken(vector.expected, other)).toThrow();
    const tampered = vector.expected.slice(0, -2) + (vector.expected.endsWith("A") ? "BB" : "AA");
    expect(() => decryptToken(tampered, key)).toThrow();
  });

  it("rejects keys that are not 32 bytes", () => {
    expect(() => parseKey(Buffer.alloc(16).toString("base64"))).toThrow(/32 bytes/);
  });
});
