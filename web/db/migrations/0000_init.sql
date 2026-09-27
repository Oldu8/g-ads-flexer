CREATE TABLE "ad_accounts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" uuid NOT NULL,
	"google_connection_id" uuid NOT NULL,
	"customer_id" text NOT NULL,
	"login_customer_id" text,
	"display_name" text DEFAULT '' NOT NULL,
	"enabled" boolean DEFAULT true NOT NULL,
	"tool_profile" text DEFAULT 'read_only' NOT NULL,
	"context" text DEFAULT '' NOT NULL,
	"fixes_sheet_id" text,
	"bearer_token_hash" text,
	"token_created_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"last_used_at" timestamp with time zone,
	CONSTRAINT "ad_accounts_bearer_token_hash_unique" UNIQUE("bearer_token_hash"),
	CONSTRAINT "ad_accounts_connection_customer_uq" UNIQUE("google_connection_id","customer_id"),
	CONSTRAINT "ad_accounts_customer_id_digits" CHECK ("ad_accounts"."customer_id" ~ '^[0-9]{10}$'),
	CONSTRAINT "ad_accounts_login_customer_id_digits" CHECK ("ad_accounts"."login_customer_id" IS NULL OR "ad_accounts"."login_customer_id" ~ '^[0-9]{10}$'),
	CONSTRAINT "ad_accounts_tool_profile" CHECK ("ad_accounts"."tool_profile" IN ('read_only', 'manager')),
	CONSTRAINT "ad_accounts_context_length" CHECK (char_length("ad_accounts"."context") <= 2000)
);
--> statement-breakpoint
CREATE TABLE "api_usage" (
	"ad_account_id" uuid NOT NULL,
	"day" date NOT NULL,
	"operations" integer DEFAULT 0 NOT NULL,
	"last_call_at" timestamp with time zone,
	CONSTRAINT "api_usage_ad_account_id_day_pk" PRIMARY KEY("ad_account_id","day")
);
--> statement-breakpoint
CREATE TABLE "google_connections" (
	"id" uuid PRIMARY KEY NOT NULL,
	"user_id" uuid NOT NULL,
	"account_id" text NOT NULL,
	"provider_id" text NOT NULL,
	"access_token" text,
	"refresh_token_enc" text,
	"id_token" text,
	"access_token_expires_at" timestamp with time zone,
	"refresh_token_expires_at" timestamp with time zone,
	"scope" text,
	"password" text,
	"revoked_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "google_connections_provider_account_uq" UNIQUE("provider_id","account_id")
);
--> statement-breakpoint
CREATE TABLE "pending_changes" (
	"id" text PRIMARY KEY NOT NULL,
	"ad_account_id" uuid NOT NULL,
	"tool_name" text NOT NULL,
	"arguments" jsonb NOT NULL,
	"preview" jsonb NOT NULL,
	"validation" text NOT NULL,
	"status" text DEFAULT 'pending' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"decided_at" timestamp with time zone,
	"result" jsonb,
	"error" text,
	"fixes_log_error" text,
	CONSTRAINT "pending_changes_validation" CHECK ("pending_changes"."validation" IN ('full', 'partial', 'none')),
	CONSTRAINT "pending_changes_status" CHECK ("pending_changes"."status" IN ('pending', 'applying', 'applied', 'failed', 'rejected', 'expired'))
);
--> statement-breakpoint
CREATE TABLE "sessions" (
	"id" uuid PRIMARY KEY NOT NULL,
	"user_id" uuid NOT NULL,
	"token" text NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"ip_address" text,
	"user_agent" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "sessions_token_unique" UNIQUE("token")
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" uuid PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"email" text NOT NULL,
	"email_verified" boolean DEFAULT false NOT NULL,
	"image" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "users_email_unique" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "verifications" (
	"id" uuid PRIMARY KEY NOT NULL,
	"identifier" text NOT NULL,
	"value" text NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "ad_accounts" ADD CONSTRAINT "ad_accounts_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "ad_accounts" ADD CONSTRAINT "ad_accounts_google_connection_id_google_connections_id_fk" FOREIGN KEY ("google_connection_id") REFERENCES "google_connections"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "api_usage" ADD CONSTRAINT "api_usage_ad_account_id_ad_accounts_id_fk" FOREIGN KEY ("ad_account_id") REFERENCES "ad_accounts"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "google_connections" ADD CONSTRAINT "google_connections_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "pending_changes" ADD CONSTRAINT "pending_changes_ad_account_id_ad_accounts_id_fk" FOREIGN KEY ("ad_account_id") REFERENCES "ad_accounts"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "ad_accounts_user_id_idx" ON "ad_accounts" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "api_usage_day_idx" ON "api_usage" USING btree ("day");--> statement-breakpoint
CREATE INDEX "google_connections_user_id_idx" ON "google_connections" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "pending_changes_account_status_idx" ON "pending_changes" USING btree ("ad_account_id","status","created_at" DESC NULLS LAST);--> statement-breakpoint
CREATE INDEX "sessions_user_id_idx" ON "sessions" USING btree ("user_id");--> statement-breakpoint
CREATE VIEW "api_usage_daily_totals" AS (select "day", sum("operations")::integer as "total_operations", count(*)::integer as "active_accounts" from "api_usage" group by "api_usage"."day");