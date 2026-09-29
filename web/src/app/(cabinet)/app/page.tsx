import Link from "next/link";
import type { Metadata } from "next";

import { GoogleSignInButton } from "@/components/auth/google-sign-in-button";
import { badge, buttonPrimary } from "@/components/ui";
import { getConnection, listAccounts } from "@/lib/cabinet";
import { formatCustomerId } from "@/lib/format";
import { hasAdsAccess } from "@/lib/google";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Your accounts" };

/** Cabinet home: the user's exposed ad accounts (spec account-connection). */
export default async function CabinetPage() {
  const { user } = await requireSession();
  const [connection, accounts] = await Promise.all([getConnection(user.id), listAccounts(user.id)]);
  const adsAccess = connection ? hasAdsAccess(connection) : false;

  return (
    <section className="mx-auto max-w-3xl px-6 py-16">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-3xl font-semibold tracking-tight">Your ad accounts</h1>
        {adsAccess ? (
          <Link href="/app/discover" className={buttonPrimary}>
            Add accounts
          </Link>
        ) : null}
      </div>

      {!adsAccess ? (
        <div className="mt-8 rounded-xl border border-line p-6">
          <p className="font-medium">Google Ads access is missing or was revoked.</p>
          <p className="mt-1 text-sm text-ink-muted">
            Sign in with Google again and allow access to Google Ads.
          </p>
          <GoogleSignInButton label="Reconnect Google" callbackURL="/app" />
        </div>
      ) : accounts.length === 0 ? (
        <div className="mt-8 rounded-xl border border-line p-6">
          <p className="font-medium">No ad accounts connected yet.</p>
          <p className="mt-1 text-sm text-ink-muted">
            Pick the Google Ads accounts your AI assistant should work with. Each one gets its
            own MCP address and its own fixes log.
          </p>
        </div>
      ) : (
        <ul className="mt-8 divide-y divide-line rounded-xl border border-line">
          {accounts.map((a) => (
            <li key={a.id}>
              <Link
                href={`/app/accounts/${a.id}`}
                className="flex items-center justify-between gap-4 px-6 py-4 hover:bg-surface"
              >
                <div>
                  <p className="font-medium">{a.displayName || "Unnamed account"}</p>
                  <p className="text-sm text-ink-muted">
                    {formatCustomerId(a.customerId)}
                    {a.lastUsedAt ? ` · last used ${a.lastUsedAt.toISOString().slice(0, 10)}` : ""}
                  </p>
                </div>
                <div className="flex gap-2 text-sm">
                  {!a.enabled ? <span className={badge}>Off</span> : null}
                  {a.toolProfile === "manager" ? <span className={badge}>Changes allowed</span> : null}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
