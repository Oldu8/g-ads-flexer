/**
 * MCP URLs: one per exposed ad account, `<MCP_PUBLIC_URL>/<mcp_slug>`
 * (ROADMAP D23). The slug says which account; it is not a secret, OAuth
 * decides who may use it. Pure functions, no env access, so they are
 * testable and usable on both server and client.
 */
import { randomBytes } from "node:crypto";

export const MCP_SLUG_PATTERN = /^[a-z0-9]{12}$/;
const ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";
const SLUG_LENGTH = 12;

/** 12 random chars of [a-z0-9], unbiased (rejection sampling). */
export function newMcpSlug(): string {
  let slug = "";
  while (slug.length < SLUG_LENGTH) {
    for (const byte of randomBytes(SLUG_LENGTH * 2)) {
      // 252 = 7 * 36: bytes above it would favour the first letters.
      if (byte < 252 && slug.length < SLUG_LENGTH) slug += ALPHABET[byte % ALPHABET.length];
    }
  }
  return slug;
}

function trimBase(base: string): string {
  return base.replace(/\/+$/, "");
}

export function mcpUrl(base: string, slug: string): string {
  return `${trimBase(base)}/${slug}`;
}

/** The slug of an account MCP URL under `base`, or null for anything else. */
export function slugFromMcpUrl(base: string, url: string): string | null {
  const prefix = `${trimBase(base)}/`;
  if (!url.startsWith(prefix)) return null;
  const slug = url.slice(prefix.length);
  return MCP_SLUG_PATTERN.test(slug) ? slug : null;
}
