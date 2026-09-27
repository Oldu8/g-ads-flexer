/**
 * What happens to OAuth tokens before Better Auth writes an account row:
 * the refresh token is encrypted, access and id tokens are never stored.
 * Pure function so it can be tested without a database or env.
 */
import { encryptToken, TOKEN_FORMAT_PREFIX } from "@/lib/token-crypto";

/** Any Better Auth account payload (full on create, partial on update). */
type TokenFields = {
  refreshToken?: string | null;
  accessToken?: string | null;
  idToken?: string | null;
  [field: string]: unknown;
};

export function protectTokens<T extends TokenFields>(data: T, key: Buffer): T {
  const out = { ...data };
  if (typeof out.refreshToken === "string" && !out.refreshToken.startsWith(TOKEN_FORMAT_PREFIX)) {
    out.refreshToken = encryptToken(out.refreshToken, key);
  }
  if ("accessToken" in out) out.accessToken = null;
  if ("idToken" in out) out.idToken = null;
  return out;
}
