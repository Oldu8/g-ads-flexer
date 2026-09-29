import "server-only";

import { mcp } from "@better-auth/mcp";
import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { APIError, createAuthMiddleware, getSessionFromCtx } from "better-auth/api";
import { nextCookies } from "better-auth/next-js";
import { jwt } from "better-auth/plugins";
import { eq } from "drizzle-orm";

import { db } from "@/db";
import * as schema from "@/db/schema";
import { protectTokens } from "@/lib/auth-hooks";
import { requiredEnv } from "@/lib/env";
import { GOOGLE_ADS_SCOPE, GOOGLE_DRIVE_FILE_SCOPE } from "@/lib/google-scopes";
import { checkMcpResources } from "@/lib/mcp-access";
import { parseKey } from "@/lib/token-crypto";


function isLoopbackOnly(uris: unknown): boolean {
  if (!Array.isArray(uris) || uris.length === 0) return false;
  return uris.every((uri) => {
    try {
      const url = new URL(String(uri));
      return url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    } catch {
      return false;
    }
  });
}

/** One access-token lifetime for every MCP client (spec account-connection). */
const MCP_ACCESS_TOKEN_SECONDS = 60 * 60;

const tokenKey = parseKey(requiredEnv("TOKEN_ENCRYPTION_KEY"));

/**
 * One Google grant signs the user in and grants Google Ads and Drive (own
 * files only) access (spec account-connection). The OAuth client must be
 * the same one the MCP server uses: a refresh token only works with the
 * client it was issued to.
 *
 * The same app is the OAuth authorization server for MCP clients (D24):
 * Claude registers itself (open DCR, public clients), the user approves on
 * /oauth/consent, and gets an ES256 JWT whose `aud` is one account's MCP URL.
 */
export const auth = betterAuth({
  baseURL: requiredEnv("BETTER_AUTH_URL"),
  secret: requiredEnv("BETTER_AUTH_SECRET"),
  database: drizzleAdapter(db, {
    provider: "pg",
    schema: {
      user: schema.users,
      session: schema.sessions,
      account: schema.googleConnections,
      verification: schema.verifications,
      oauthClient: schema.oauthClients,
      oauthResource: schema.oauthResources,
      oauthClientResource: schema.oauthClientResources,
      oauthRefreshToken: schema.oauthRefreshTokens,
      oauthAccessToken: schema.oauthAccessTokens,
      oauthConsent: schema.oauthConsents,
      oauthClientAssertion: schema.oauthClientAssertions,
      jwks: schema.jwks,
    },
  }),
  advanced: { database: { generateId: "uuid" } },
  // jwt()'s session-to-JWT endpoint: MCP tokens only come from /oauth2/token.
  disabledPaths: ["/token"],
  socialProviders: {
    google: {
      clientId: requiredEnv("GOOGLE_CLIENT_ID"),
      clientSecret: requiredEnv("GOOGLE_CLIENT_SECRET"),
      scope: [GOOGLE_ADS_SCOPE, GOOGLE_DRIVE_FILE_SCOPE],
      // Always return a refresh token, also on later sign-ins.
      accessType: "offline",
      prompt: "select_account consent",
    },
  },
  hooks: {
    before: createAuthMiddleware(async (ctx) => {
      // RFC 7591 defaults application_type to "web", and Better Auth refuses
      // loopback redirects for web clients. Clients that register only
      // http://localhost / 127.0.0.1 callbacks without a type (Claude Code)
      // are native apps (OIDC Registration §2), so register them as such.
      if (ctx.path === "/oauth2/register") {
        const body = (ctx.body ?? {}) as { application_type?: string; redirect_uris?: unknown };
        if (!body.application_type && isLoopbackOnly(body.redirect_uris)) {
          return { context: { body: { ...body, application_type: "native" } } };
        }
        return;
      }
      // Refuse consent for anything but the user's own enabled account, so no
      // authorization code is issued for it (token issuance checks again).
      if (ctx.path === "/oauth2/consent" && ctx.body?.accept === true) {
        const query = new URLSearchParams(String(ctx.body?.oauth_query ?? ""));
        const session = await getSessionFromCtx(ctx);
        const check = await checkMcpResources(session?.user.id, query.getAll("resource"));
        if (!check.ok) {
          throw new APIError("FORBIDDEN", {
            error: "invalid_target",
            error_description: "The requested ad account is not available to this user",
          });
        }
      }
    }),
  },
  databaseHooks: {
    account: {
      create: {
        before: async (account) => ({ data: protectTokens(account, tokenKey) }),
      },
      update: {
        before: async (data) => ({ data: protectTokens(data, tokenKey) }),
        // A successful sign-in means the grant is valid again.
        after: async (account) => {
          await db
            .update(schema.googleConnections)
            .set({ revokedAt: null })
            .where(eq(schema.googleConnections.id, account.id));
        },
      },
    },
  },
  plugins: [
    // FastMCP's JWTVerifier has no EdDSA (the jwt() default).
    jwt({ jwks: { keyPairConfig: { alg: "ES256" } } }),
    mcp({
      // Canonical resource; every account adds its own row (its MCP URL).
      resource: requiredEnv("MCP_PUBLIC_URL"),
      loginPage: "/login",
      consentPage: "/oauth/consent",
      // Claude falls back to dynamic registration without CIMD (ROADMAP D24).
      allowDynamicClientRegistration: true,
      allowUnauthenticatedClientRegistration: true,
      // MCP needs no identity scopes: offline_access alone gives Claude a
      // refresh token and keeps `aud` to the account URL (openid would add
      // the userinfo endpoint).
      clientRegistrationDefaultScopes: ["offline_access"],
      clientRegistrationAllowedScopes: ["openid", "profile", "email"],
      // Account resources are created at runtime, not linked per client;
      // ownership is checked below instead.
      enforcePerClientResources: false,
      accessTokenExpiresIn: MCP_ACCESS_TOKEN_SECONDS,
      // No signed-in user may manage clients or resources through the
      // plugin's admin endpoints (its default allows any session).
      clientPrivileges: () => false,
      resourcePrivileges: () => false,
      // Runs at every JWT issuance, refreshes included: the token's
      // resources must be the user's own enabled accounts.
      customAccessTokenClaims: async ({ user, resources }) => {
        const check = await checkMcpResources(user?.id, resources);
        if (!check.ok) {
          throw new APIError("BAD_REQUEST", {
            error: "invalid_target",
            error_description: "The requested ad account is not available to this user",
          });
        }
        return {};
      },
    }),
    nextCookies(),
  ],
});

export type Session = typeof auth.$Infer.Session;
