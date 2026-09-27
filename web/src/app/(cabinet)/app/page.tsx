import { and, eq } from "drizzle-orm";
import type { Metadata } from "next";

import { db } from "@/db";
import { googleConnections } from "@/db/schema";
import { GOOGLE_ADS_SCOPE } from "@/lib/auth";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Your accounts" };

/** Cabinet home. Account discovery and MCP connections: web track B2. */
export default async function CabinetPage() {
  const session = await requireSession();
  const [connection] = await db
    .select({
      scope: googleConnections.scope,
      hasRefreshToken: googleConnections.refreshToken,
      revokedAt: googleConnections.revokedAt,
    })
    .from(googleConnections)
    .where(
      and(
        eq(googleConnections.userId, session.user.id),
        eq(googleConnections.providerId, "google"),
      ),
    )
    .limit(1);

  const adsAccess =
    connection &&
    !connection.revokedAt &&
    Boolean(connection.hasRefreshToken) &&
    (connection.scope ?? "").includes(GOOGLE_ADS_SCOPE);

  return (
    <section className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Your ad accounts</h1>
      <div className="mt-8 rounded-xl border border-line p-6">
        <p className="text-sm text-ink-muted">Google Ads access</p>
        <p className="mt-1 text-lg font-medium">
          {adsAccess ? "Granted" : "Not granted — sign out and sign in again"}
        </p>
      </div>
      <p className="mt-6 text-ink-muted">
        Choosing ad accounts and connecting them to your AI assistant is coming next.
      </p>
    </section>
  );
}
