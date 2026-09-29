import { eq } from "drizzle-orm";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Logo } from "@/components/logo";
import { db } from "@/db";
import { oauthClients } from "@/db/schema";
import { formatCustomerId } from "@/lib/format";
import { checkMcpResources } from "@/lib/mcp-access";
import { getSession } from "@/lib/session";

import { ConsentButtons } from "./consent-buttons";

export const metadata: Metadata = { title: "Connect an AI assistant" };

/**
 * Consent for an MCP client (spec account-connection, "MCP clients get
 * access through OAuth"). Better Auth redirects here with a signed query;
 * the query is only displayed here, the consent endpoint verifies it and
 * re-checks that the account is the user's own.
 */
export default async function ConsentPage(props: PageProps<"/oauth/consent">) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(await props.searchParams)) {
    for (const v of Array.isArray(value) ? value : [value]) if (v !== undefined) params.append(key, v);
  }
  const session = await getSession();
  if (!session) redirect(`/login?${params.toString()}`);

  const clientId = params.get("client_id");
  const [client] = clientId
    ? await db
        .select({ name: oauthClients.name, uri: oauthClients.uri })
        .from(oauthClients)
        .where(eq(oauthClients.clientId, clientId))
        .limit(1)
    : [];
  const check = await checkMcpResources(session.user.id, params.getAll("resource"));
  const clientName = client?.name?.trim() || "An AI assistant";
  const account = check.ok ? check.accounts[0] : undefined;

  return (
    <main className="flex flex-1 items-center justify-center bg-surface px-6 py-16">
      <div className="w-full max-w-md rounded-xl border border-line bg-white p-8">
        <Logo />
        {!params.get("sig") || !client ? (
          <>
            <h1 className="mt-6 text-2xl font-semibold tracking-tight">This link is not valid</h1>
            <p className="mt-2 text-sm text-ink-muted">
              Start the connection again from your AI assistant.
            </p>
          </>
        ) : !account ? (
          <>
            <h1 className="mt-6 text-2xl font-semibold tracking-tight">Account not available</h1>
            <p className="mt-2 text-sm text-ink-muted">
              {clientName} asked for an ad account that is not connected to{" "}
              {session.user.email}, or is switched off. Check the address you added in{" "}
              {clientName}: copy it from the account page in your cabinet.
            </p>
            <ConsentButtons canAllow={false} />
          </>
        ) : (
          <>
            <h1 className="mt-6 text-2xl font-semibold tracking-tight">
              Connect {clientName} to {account.displayName || "your ad account"}?
            </h1>
            <p className="mt-2 text-sm text-ink-muted">
              Google Ads account {formatCustomerId(account.customerId)}, signed in as{" "}
              {session.user.email}.
            </p>
            <ul className="mt-6 space-y-2 text-sm">
              <li>• Read reports and settings of this account.</li>
              {account.toolProfile === "manager" ? (
                <li>• Propose changes. Nothing is applied until you approve it in the chat.</li>
              ) : (
                <li>• No changes: this account is read-only (you can allow changes in the cabinet).</li>
              )}
              <li>• Keep the account&apos;s fixes log in your Google Drive.</li>
            </ul>
            <p className="mt-4 text-xs text-ink-muted">
              Only this ad account. You can disconnect {clientName} any time on the account page.
            </p>
            <ConsentButtons canAllow />
          </>
        )}
      </div>
    </main>
  );
}
