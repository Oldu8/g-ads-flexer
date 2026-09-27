import "server-only";

import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { nextCookies } from "better-auth/next-js";
import { eq } from "drizzle-orm";

import { db } from "@/db";
import * as schema from "@/db/schema";
import { protectTokens } from "@/lib/auth-hooks";
import { requiredEnv } from "@/lib/env";
import { parseKey } from "@/lib/token-crypto";

export const GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords";

const tokenKey = parseKey(requiredEnv("TOKEN_ENCRYPTION_KEY"));

/**
 * One Google grant signs the user in and grants Google Ads access (spec
 * account-connection). The OAuth client must be the same one the MCP
 * server uses: a refresh token only works with the client it was issued to.
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
    },
  }),
  advanced: { database: { generateId: "uuid" } },
  socialProviders: {
    google: {
      clientId: requiredEnv("GOOGLE_CLIENT_ID"),
      clientSecret: requiredEnv("GOOGLE_CLIENT_SECRET"),
      scope: [GOOGLE_ADS_SCOPE],
      // Always return a refresh token, also on later sign-ins.
      accessType: "offline",
      prompt: "select_account consent",
    },
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
  plugins: [nextCookies()],
});

export type Session = typeof auth.$Infer.Session;
