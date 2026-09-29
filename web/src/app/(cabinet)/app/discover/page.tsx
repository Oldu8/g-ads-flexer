import Link from "next/link";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { saveDiscoveredAction } from "@/app/(cabinet)/app/actions";
import { GoogleSignInButton } from "@/components/auth/google-sign-in-button";
import { buttonPrimary, textLink } from "@/components/ui";
import { getConnection, listAccounts } from "@/lib/cabinet";
import type { OfferedAccount } from "@/lib/discovery";
import { formatCustomerId } from "@/lib/format";
import { discoverAccounts, GoogleGrantRevokedError, hasAdsAccess } from "@/lib/google";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Add ad accounts" };

/** Live discovery: every enabled ad account the Google grant reaches. */
export default async function DiscoverPage() {
  const { user } = await requireSession();
  const connection = await getConnection(user.id);
  if (!connection || !hasAdsAccess(connection)) redirect("/app");

  let discovery: Awaited<ReturnType<typeof discoverAccounts>>;
  try {
    discovery = await discoverAccounts(connection);
  } catch (error) {
    const revoked = error instanceof GoogleGrantRevokedError;
    return (
      <section className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">Add ad accounts</h1>
        <div className="mt-8 rounded-xl border border-line p-6">
          <p className="font-medium">
            {revoked ? "Google access was revoked." : "Google Ads did not answer."}
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            {revoked ? "Sign in with Google again." : "Try again in a minute."}
          </p>
          {revoked ? <GoogleSignInButton label="Reconnect Google" callbackURL="/app/discover" /> : null}
        </div>
      </section>
    );
  }

  const added = new Set((await listAccounts(user.id)).map((a) => a.customerId));
  const groups = new Map<string, OfferedAccount[]>();
  for (const account of discovery.accounts) {
    const key = account.loginCustomerId ?? "";
    groups.set(key, [...(groups.get(key) ?? []), account]);
  }
  const groupTitle = (key: string) =>
    key === ""
      ? "Direct access"
      : `Through ${discovery.managers[key] || "manager"} (${formatCustomerId(key)})`;
  const anyNew = discovery.accounts.some((a) => !added.has(a.customerId));

  return (
    <section className="mx-auto max-w-3xl px-6 py-16">
      <Link href="/app" className={`${textLink} text-sm`}>
        ← Your ad accounts
      </Link>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">Add ad accounts</h1>
      <p className="mt-2 text-ink-muted">
        Each account you add gets its own MCP address for Claude and its own fixes-log sheet in
        your Google Drive. Changes stay off until you allow them.
      </p>

      {discovery.accounts.length === 0 ? (
        <p className="mt-8 rounded-xl border border-line p-6">
          No enabled ad accounts are reachable with this Google account.
        </p>
      ) : (
        <form action={saveDiscoveredAction} className="mt-8 space-y-6">
          {[...groups.entries()].map(([key, accounts]) => (
            <fieldset key={key} className="rounded-xl border border-line">
              <legend className="ml-4 px-2 text-sm text-ink-muted">{groupTitle(key)}</legend>
              <ul className="divide-y divide-line">
                {accounts.map((a) => {
                  const isAdded = added.has(a.customerId);
                  return (
                    <li key={a.customerId}>
                      <label className="flex cursor-pointer items-center gap-4 px-6 py-3 hover:bg-surface">
                        <input
                          type="checkbox"
                          name="customer"
                          value={a.customerId}
                          defaultChecked={isAdded}
                          disabled={isAdded}
                          className="size-4 accent-primary"
                        />
                        <span className="flex-1">
                          <span className="font-medium">{a.displayName || "Unnamed account"}</span>{" "}
                          <span className="text-sm text-ink-muted">{formatCustomerId(a.customerId)}</span>
                        </span>
                        {isAdded ? <span className="text-sm text-ink-muted">Added</span> : null}
                      </label>
                    </li>
                  );
                })}
              </ul>
            </fieldset>
          ))}
          {discovery.failedRoots.length > 0 ? (
            <p className="text-sm text-ink-muted">
              {discovery.failedRoots.length} account(s) could not be read (for example cancelled
              ones) and are not listed.
            </p>
          ) : null}
          <button type="submit" disabled={!anyNew} className={buttonPrimary}>
            Add selected accounts
          </button>
        </form>
      )}
    </section>
  );
}
