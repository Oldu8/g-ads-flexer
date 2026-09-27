/**
 * The platform's shared database schema (ROADMAP D9-D11, spec
 * openspec/changes/platform-db-and-cabinet/specs/platform-schema).
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

export const users = pgTable("users", {
  id: uuid("id").primaryKey(),
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
    id: uuid("id").primaryKey(),
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
    id: uuid("id").primaryKey(),
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
  id: uuid("id").primaryKey(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  createdAt: createdAt(),
  updatedAt: updatedAt(),
});

// --- Platform ----------------------------------------------------------------

/** One Google Ads account a user exposes over MCP (own bearer token). */
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
    bearerTokenHash: text("bearer_token_hash").unique(),
    tokenCreatedAt: timestamp("token_created_at", { withTimezone: true }),
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
