/**
 * The platform's shared database schema (ROADMAP D9-D11, spec
 * openspec/specs/platform-schema).
 *
 * Tables are unqualified: the connecting role's search_path picks the
 * schema (`app` for prod, `app_dev` for dev), so one set of migrations
 * serves both. TS property names follow Better Auth's field names; DB
 * column names are snake_case.
 */
import { sql } from "drizzle-orm";
import {
  boolean,
  check,
  date,
  index,
  integer,
  jsonb,
  pgTable,
  pgView,
  primaryKey,
  text,
  timestamp,
  unique,
  uuid,
} from "drizzle-orm/pg-core";

const createdAt = () => timestamp("created_at", { withTimezone: true }).notNull().defaultNow();
const updatedAt = () => timestamp("updated_at", { withTimezone: true }).notNull().defaultNow();

// --- Better Auth core (user, session, account, verification) -----------------
// With `generateId: "uuid"` on Postgres, Better Auth leaves ids to the
// database, so every id column needs a default.

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: boolean("email_verified").notNull().default(false),
  image: text("image"),
  createdAt: createdAt(),
  updatedAt: updatedAt(),
});

export const sessions = pgTable(
  "sessions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    token: text("token").notNull().unique(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    ipAddress: text("ip_address"),
    userAgent: text("user_agent"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [index("sessions_user_id_idx").on(t.userId)],
);

/**
 * One Google OAuth grant (Better Auth's `account` model). The refresh token
 * is stored only as AES-256-GCM ciphertext (`refresh_token_enc`, encrypted
 * in the auth database hook); access and id tokens are never stored.
 */
export const googleConnections = pgTable(
  "google_connections",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    accountId: text("account_id").notNull(), // Google `sub`
    providerId: text("provider_id").notNull(),
    accessToken: text("access_token"),
    refreshToken: text("refresh_token_enc"),
    idToken: text("id_token"),
    accessTokenExpiresAt: timestamp("access_token_expires_at", { withTimezone: true }),
    refreshTokenExpiresAt: timestamp("refresh_token_expires_at", { withTimezone: true }),
    scope: text("scope"),
    password: text("password"),
    revokedAt: timestamp("revoked_at", { withTimezone: true }),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    unique("google_connections_provider_account_uq").on(t.providerId, t.accountId),
    index("google_connections_user_id_idx").on(t.userId),
  ],
);

export const verifications = pgTable("verifications", {
  id: uuid("id").primaryKey().defaultRandom(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  createdAt: createdAt(),
  updatedAt: updatedAt(),
});

// --- OAuth authorization server for MCP clients ------------------------------
// Models of @better-auth/oauth-provider (via @better-auth/mcp) and the jwt()
// plugin. Only web/ touches them; the MCP server verifies tokens with the
// public JWKS over HTTPS (spec platform-schema, "MCP access-token format").
// Optional Better Auth dates are nullable; ids that point at users, sessions
// or other uuid rows are uuids, client ids are Better Auth's random strings.

export const oauthClients = pgTable(
  "oauth_clients",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    clientId: text("client_id").notNull().unique(),
    clientSecret: text("client_secret"),
    clientDiscoveryId: text("client_discovery_id"),
    disabled: boolean("disabled").default(false),
    skipConsent: boolean("skip_consent"),
    enableEndSession: boolean("enable_end_session"),
    subjectType: text("subject_type"),
    scopes: text("scopes").array(),
    clientCredentialsScopes: text("client_credentials_scopes").array(),
    userId: uuid("user_id").references(() => users.id, { onDelete: "cascade" }),
    createdAt: timestamp("created_at", { withTimezone: true }),
    updatedAt: timestamp("updated_at", { withTimezone: true }),
    name: text("name"),
    uri: text("uri"),
    icon: text("icon"),
    contacts: text("contacts").array(),
    tos: text("tos"),
    policy: text("policy"),
    softwareId: text("software_id"),
    softwareVersion: text("software_version"),
    softwareStatement: text("software_statement"),
    redirectUris: text("redirect_uris").array().notNull(),
    postLogoutRedirectUris: text("post_logout_redirect_uris").array(),
    backchannelLogoutUri: text("backchannel_logout_uri"),
    backchannelLogoutSessionRequired: boolean("backchannel_logout_session_required"),
    tokenEndpointAuthMethod: text("token_endpoint_auth_method"),
    applicationType: text("application_type"),
    jwks: text("jwks"),
    jwksUri: text("jwks_uri"),
    grantTypes: text("grant_types").array(),
    responseTypes: text("response_types").array(),
    requirePKCE: boolean("require_pkce"),
    dpopBoundAccessTokens: boolean("dpop_bound_access_tokens").default(false),
    referenceId: text("reference_id"),
    metadata: jsonb("metadata"),
  },
  (t) => [index("oauth_clients_user_id_idx").on(t.userId)],
);

/** One protected resource per exposed ad account: identifier = its MCP URL. */
export const oauthResources = pgTable("oauth_resources", {
  id: uuid("id").primaryKey().defaultRandom(),
  identifier: text("identifier").notNull().unique(),
  name: text("name").notNull(),
  accessTokenTtl: integer("access_token_ttl"),
  refreshTokenTtl: integer("refresh_token_ttl"),
  signingAlgorithm: text("signing_algorithm"),
  signingKeyId: text("signing_key_id"),
  allowedScopes: text("allowed_scopes").array(),
  customClaims: jsonb("custom_claims"),
  dpopBoundAccessTokensRequired: boolean("dpop_bound_access_tokens_required").default(false),
  disabled: boolean("disabled").default(false),
  createdAt: timestamp("created_at", { withTimezone: true }),
  updatedAt: timestamp("updated_at", { withTimezone: true }),
  policyVersion: integer("policy_version").default(1),
  metadata: jsonb("metadata"),
});

export const oauthClientResources = pgTable(
  "oauth_client_resources",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    clientId: text("client_id")
      .notNull()
      .references(() => oauthClients.clientId, { onDelete: "cascade" }),
    resourceId: text("resource_id")
      .notNull()
      .references(() => oauthResources.identifier, { onDelete: "cascade" }),
    metadata: jsonb("metadata"),
    createdAt: timestamp("created_at", { withTimezone: true }),
  },
  (t) => [
    unique("oauth_client_resources_client_resource_uq").on(t.clientId, t.resourceId),
    index("oauth_client_resources_resource_id_idx").on(t.resourceId),
  ],
);

export const oauthRefreshTokens = pgTable(
  "oauth_refresh_tokens",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    token: text("token").notNull().unique(),
    clientId: text("client_id")
      .notNull()
      .references(() => oauthClients.clientId, { onDelete: "cascade" }),
    sessionId: uuid("session_id").references(() => sessions.id, { onDelete: "set null" }),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    referenceId: text("reference_id"),
    authorizationCodeId: text("authorization_code_id"),
    resources: text("resources").array(),
    requestedUserInfoClaims: text("requested_user_info_claims").array(),
    expiresAt: timestamp("expires_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }),
    revoked: timestamp("revoked", { withTimezone: true }),
    rotatedAt: timestamp("rotated_at", { withTimezone: true }),
    rotationReplayResponse: text("rotation_replay_response"),
    rotationReplayExpiresAt: timestamp("rotation_replay_expires_at", { withTimezone: true }),
    authTime: timestamp("auth_time", { withTimezone: true }),
    confirmation: jsonb("confirmation"),
    scopes: text("scopes").array().notNull(),
  },
  (t) => [
    index("oauth_refresh_tokens_client_id_idx").on(t.clientId),
    index("oauth_refresh_tokens_user_id_idx").on(t.userId),
    index("oauth_refresh_tokens_session_id_idx").on(t.sessionId),
    index("oauth_refresh_tokens_authorization_code_id_idx").on(t.authorizationCodeId),
  ],
);

export const oauthAccessTokens = pgTable(
  "oauth_access_tokens",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    token: text("token").unique(),
    clientId: text("client_id")
      .notNull()
      .references(() => oauthClients.clientId, { onDelete: "cascade" }),
    sessionId: uuid("session_id").references(() => sessions.id, { onDelete: "set null" }),
    userId: uuid("user_id").references(() => users.id, { onDelete: "cascade" }),
    referenceId: text("reference_id"),
    authorizationCodeId: text("authorization_code_id"),
    resources: text("resources").array(),
    requestedUserInfoClaims: text("requested_user_info_claims").array(),
    refreshId: uuid("refresh_id").references(() => oauthRefreshTokens.id, { onDelete: "cascade" }),
    expiresAt: timestamp("expires_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }),
    revoked: timestamp("revoked", { withTimezone: true }),
    confirmation: jsonb("confirmation"),
    scopes: text("scopes").array().notNull(),
  },
  (t) => [
    index("oauth_access_tokens_client_id_idx").on(t.clientId),
    index("oauth_access_tokens_user_id_idx").on(t.userId),
    index("oauth_access_tokens_session_id_idx").on(t.sessionId),
    index("oauth_access_tokens_refresh_id_idx").on(t.refreshId),
    index("oauth_access_tokens_authorization_code_id_idx").on(t.authorizationCodeId),
  ],
);

export const oauthConsents = pgTable(
  "oauth_consents",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    clientId: text("client_id")
      .notNull()
      .references(() => oauthClients.clientId, { onDelete: "cascade" }),
    userId: uuid("user_id").references(() => users.id, { onDelete: "cascade" }),
    referenceId: text("reference_id"),
    resources: text("resources").array(),
    requestedUserInfoClaims: text("requested_user_info_claims").array(),
    scopes: text("scopes").array().notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }),
    updatedAt: timestamp("updated_at", { withTimezone: true }),
  },
  (t) => [
    index("oauth_consents_client_id_idx").on(t.clientId),
    index("oauth_consents_user_id_idx").on(t.userId),
  ],
);

/** Replay guard for `private_key_jwt` client assertions. */
export const oauthClientAssertions = pgTable("oauth_client_assertions", {
  id: text("id").primaryKey(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
});

/** Signing keys of the jwt() plugin; private keys are encrypted by Better Auth. */
export const jwks = pgTable("jwks", {
  id: uuid("id").primaryKey().defaultRandom(),
  publicKey: text("public_key").notNull(),
  privateKey: text("private_key").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
  expiresAt: timestamp("expires_at", { withTimezone: true }),
  alg: text("alg"),
  crv: text("crv"),
});

// --- Platform ----------------------------------------------------------------

/**
 * One Google Ads account a user exposes over MCP. Its MCP URL is
 * `<MCP_PUBLIC_URL>/<mcp_slug>`; MCP clients get access to it through OAuth
 * (an `oauth_resources` row with that URL), never through a static token.
 */
export const adAccounts = pgTable(
  "ad_accounts",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    googleConnectionId: uuid("google_connection_id")
      .notNull()
      .references(() => googleConnections.id, { onDelete: "cascade" }),
    customerId: text("customer_id").notNull(),
    loginCustomerId: text("login_customer_id"),
    displayName: text("display_name").notNull().default(""),
    enabled: boolean("enabled").notNull().default(true),
    toolProfile: text("tool_profile").notNull().default("read_only"),
    context: text("context").notNull().default(""),
    fixesSheetId: text("fixes_sheet_id"),
    mcpSlug: text("mcp_slug").notNull().unique(),
    createdAt: createdAt(),
    lastUsedAt: timestamp("last_used_at", { withTimezone: true }),
  },
  (t) => [
    unique("ad_accounts_connection_customer_uq").on(t.googleConnectionId, t.customerId),
    index("ad_accounts_user_id_idx").on(t.userId),
    check("ad_accounts_customer_id_digits", sql`${t.customerId} ~ '^[0-9]{10}$'`),
    check(
      "ad_accounts_login_customer_id_digits",
      sql`${t.loginCustomerId} IS NULL OR ${t.loginCustomerId} ~ '^[0-9]{10}$'`,
    ),
    check("ad_accounts_tool_profile", sql`${t.toolProfile} IN ('read_only', 'manager')`),
    check("ad_accounts_context_length", sql`char_length(${t.context}) <= 2000`),
    check("ad_accounts_mcp_slug_format", sql`${t.mcpSlug} ~ '^[a-z0-9]{12}$'`),
  ],
);

/** The write queue (Phase C): every Google Ads write is queued here first. */
export const pendingChanges = pgTable(
  "pending_changes",
  {
    id: text("id").primaryKey(), // pc_ + 12 hex
    adAccountId: uuid("ad_account_id")
      .notNull()
      .references(() => adAccounts.id, { onDelete: "cascade" }),
    toolName: text("tool_name").notNull(),
    arguments: jsonb("arguments").notNull(),
    preview: jsonb("preview").notNull(),
    validation: text("validation").notNull(),
    status: text("status").notNull().default("pending"),
    createdAt: createdAt(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    decidedAt: timestamp("decided_at", { withTimezone: true }),
    result: jsonb("result"),
    error: text("error"),
    fixesLogError: text("fixes_log_error"),
  },
  (t) => [
    index("pending_changes_account_status_idx").on(t.adAccountId, t.status, t.createdAt.desc()),
    check("pending_changes_validation", sql`${t.validation} IN ('full', 'partial', 'none')`),
    check(
      "pending_changes_status",
      sql`${t.status} IN ('pending', 'applying', 'applied', 'failed', 'rejected', 'expired')`,
    ),
  ],
);

/** Google Ads API operations per account per quota day (America/Los_Angeles). */
export const apiUsage = pgTable(
  "api_usage",
  {
    adAccountId: uuid("ad_account_id")
      .notNull()
      .references(() => adAccounts.id, { onDelete: "cascade" }),
    day: date("day").notNull(),
    operations: integer("operations").notNull().default(0),
    lastCallAt: timestamp("last_call_at", { withTimezone: true }),
  },
  (t) => [primaryKey({ columns: [t.adAccountId, t.day] }), index("api_usage_day_idx").on(t.day)],
);

export const apiUsageDailyTotals = pgView("api_usage_daily_totals").as((qb) =>
  qb
    .select({
      day: apiUsage.day,
      totalOperations: sql<number>`sum(${apiUsage.operations})::integer`.as("total_operations"),
      activeAccounts: sql<number>`count(*)::integer`.as("active_accounts"),
    })
    .from(apiUsage)
    .groupBy(apiUsage.day),
);
