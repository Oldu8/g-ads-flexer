ALTER TABLE "ad_accounts" ADD COLUMN "mcp_slug" text NOT NULL;--> statement-breakpoint
ALTER TABLE "ad_accounts" ADD CONSTRAINT "ad_accounts_mcp_slug_unique" UNIQUE("mcp_slug");--> statement-breakpoint
ALTER TABLE "ad_accounts" ADD CONSTRAINT "ad_accounts_mcp_slug_format" CHECK ("ad_accounts"."mcp_slug" ~ '^[a-z0-9]{12}$');