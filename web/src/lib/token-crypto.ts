/**
 * Refresh-token encryption shared with the Python MCP server
 * (spec platform-schema, "Refresh-token encryption format").
 *
 * Format: `v1.` + base64url(no padding) of nonce(12) || ciphertext || tag(16),
 * AES-256-GCM, 32-byte key from TOKEN_ENCRYPTION_KEY (base64), associated
 * data = TOKEN_AAD. Both languages are checked against
 * db/test-vectors/token-encryption.json.
 *
 * The associated data is a fixed context string, not the row's Google
 * `sub`: Better Auth's account-update hook only sees the changed fields, so
 * the row is unknown when a token is re-encrypted on a later sign-in.
 */
import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

export const TOKEN_FORMAT_PREFIX = "v1.";
export const TOKEN_AAD = "adsmigo:google_connections.refresh_token_enc:v1";
const NONCE_BYTES = 12;
const TAG_BYTES = 16;

export function parseKey(base64Key: string): Buffer {
  const key = Buffer.from(base64Key, "base64");
  if (key.length !== 32) {
    throw new Error("TOKEN_ENCRYPTION_KEY must be 32 bytes, base64-encoded");
  }
  return key;
}

export function encryptToken(plaintext: string, key: Buffer, nonce?: Buffer): string {
  const iv = nonce ?? randomBytes(NONCE_BYTES);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  cipher.setAAD(Buffer.from(TOKEN_AAD, "utf8"));
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const blob = Buffer.concat([iv, ciphertext, cipher.getAuthTag()]);
  return TOKEN_FORMAT_PREFIX + blob.toString("base64url");
}

export function decryptToken(value: string, key: Buffer): string {
  if (!value.startsWith(TOKEN_FORMAT_PREFIX)) {
    throw new Error("unsupported token format");
  }
  const blob = Buffer.from(value.slice(TOKEN_FORMAT_PREFIX.length), "base64url");
  if (blob.length < NONCE_BYTES + TAG_BYTES) throw new Error("token ciphertext too short");
  const iv = blob.subarray(0, NONCE_BYTES);
  const tag = blob.subarray(blob.length - TAG_BYTES);
  const ciphertext = blob.subarray(NONCE_BYTES, blob.length - TAG_BYTES);
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAAD(Buffer.from(TOKEN_AAD, "utf8"));
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
}
