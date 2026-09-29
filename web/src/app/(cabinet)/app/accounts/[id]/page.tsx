import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  createSheetAction,
  disconnectClientAction,
  removeAccountAction,
  setAllowChangesAction,
  setEnabledAction,
} from "@/app/(cabinet)/app/actions";
import { GoogleSignInButton } from "@/components/auth/google-sign-in-button";
import { ContextForm } from "@/components/cabinet/context-form";
import { CopyButton } from "@/components/cabinet/copy-button";
import { buttonPrimary, buttonSecondary, textLink } from "@/components/ui";
import {
  accountMcpUrl,
  getAccount,
  getConnection,
  listConnectedClients,
  sheetStatus,
} from "@/lib/cabinet";
import { sheetUrl } from "@/lib/fixes-sheet";
import { formatCustomerId } from "@/lib/format";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Ad account" };

const day = (value: string | Date | null) =>
  value ? new Date(value).toISOString().slice(0, 10) : "—";

const card = "rounded-xl border border-line p-6";
const smallButton = "px-4 py-2 text-sm";

/** One exposed account: MCP address, clients, switches, context, fixes log. */
export default async function AccountPage(props: PageProps<"/app/accounts/[id]">) {
  const { id } = await props.params;
  const { user } = await requireSession();
  const account = await getAccount(user.id, id);
  if (!account) notFound();
  const connection = await getConnection(user.id);
  const [clients, sheet] = await Promise.all([
    listConnectedClients(user.id, account),
    sheetStatus(account, connection),
  ]);
  const url = accountMcpUrl(account.mcpSlug);
  const name = account.displayName || "Unnamed account";
  const allowChanges = account.toolProfile === "manager";

  return (
    <section className="mx-auto max-w-3xl px-6 py-16">
      <Link href="/app" className={`${textLink} text-sm`}>
        ← Your ad accounts
      </Link>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">{name}</h1>
      <p className="mt-1 text-ink-muted">
        Google Ads {formatCustomerId(account.customerId)}
        {account.loginCustomerId ? ` · through manager ${formatCustomerId(account.loginCustomerId)}` : ""}
      </p>

      <div className="mt-8 space-y-6">
        <div className={card}>
          <h2 className="text-lg font-semibold">Connect to Claude</h2>
          <div className="mt-4 flex items-center gap-3">
            <code className="flex-1 truncate rounded-lg bg-surface px-3 py-2 text-sm">{url}</code>
            <CopyButton value={url} />
          </div>
          <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm text-ink-muted">
            <li>
              In Claude Desktop or claude.ai open Settings → Connectors → Add custom connector.
            </li>
            <li>
              Name it <span className="text-ink">Ads · {name}</span> and paste this address.
            </li>
            <li>Click Connect, sign in with this Google account and allow access.</li>
          </ol>
          <p className="mt-3 text-xs text-ink-muted">
            This address is for this ad account only; every account is a separate connector. It
            is not a password: only you can approve access to it.
          </p>

          <h3 className="mt-6 text-sm font-semibold">Connected assistants</h3>
          {clients.length === 0 ? (
            <p className="mt-2 text-sm text-ink-muted">None yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {clients.map((c) => (
                <li key={c.clientId} className="flex items-center justify-between gap-4 py-2 text-sm">
                  <span>
                    {c.name || "Unnamed client"}
                    <span className="text-ink-muted">
                      {" "}
                      · connected {day(c.connectedAt)} · last refreshed {day(c.lastRefreshedAt)}
                    </span>
                  </span>
                  <form action={disconnectClientAction}>
                    <input type="hidden" name="id" value={account.id} />
                    <input type="hidden" name="clientId" value={c.clientId} />
                    <button type="submit" className={`${buttonSecondary} ${smallButton}`}>
                      Disconnect
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className={card}>
          <h2 className="text-lg font-semibold">Access</h2>
          <div className="mt-4 flex items-center justify-between gap-4">
            <div>
              <p className="font-medium">{account.enabled ? "On" : "Off"}</p>
              <p className="text-sm text-ink-muted">
                When off, every connected assistant loses access immediately.
              </p>
            </div>
            <form action={setEnabledAction}>
              <input type="hidden" name="id" value={account.id} />
              <input type="hidden" name="enabled" value={String(!account.enabled)} />
              <button type="submit" className={`${buttonSecondary} ${smallButton}`}>
                {account.enabled ? "Switch off" : "Switch on"}
              </button>
            </form>
          </div>
          <div className="mt-6 flex items-center justify-between gap-4">
            <div>
              <p className="font-medium">{allowChanges ? "Changes allowed" : "Read-only"}</p>
              <p className="text-sm text-ink-muted">
                {allowChanges
                  ? "The assistant can propose changes; each one waits for your approval in the chat."
                  : "The assistant can only read reports and settings."}
              </p>
            </div>
            <form action={setAllowChangesAction}>
              <input type="hidden" name="id" value={account.id} />
              <input type="hidden" name="allow" value={String(!allowChanges)} />
              <button type="submit" className={`${buttonSecondary} ${smallButton}`}>
                {allowChanges ? "Make read-only" : "Allow changes"}
              </button>
            </form>
          </div>
        </div>

        <div className={card}>
          <h2 className="text-lg font-semibold">Business context</h2>
          <p className="mt-1 text-sm text-ink-muted">
            The assistant sees this with every conversation about this account.
          </p>
          <ContextForm id={account.id} initial={account.context} />
        </div>

        <div className={card}>
          <h2 className="text-lg font-semibold">Fixes log</h2>
          <p className="mt-1 text-sm text-ink-muted">
            A Google Sheet in your Drive where the assistant records every change and its
            expected outcome, and reviews it later.
          </p>
          <div className="mt-4">
            {sheet === "ok" && account.fixesSheetId ? (
              <a href={sheetUrl(account.fixesSheetId)} target="_blank" rel="noreferrer" className={textLink}>
                Open the fixes log ↗
              </a>
            ) : sheet === "unknown" && account.fixesSheetId ? (
              <p className="text-sm text-ink-muted">
                Google Drive did not answer.{" "}
                <a href={sheetUrl(account.fixesSheetId)} target="_blank" rel="noreferrer" className={textLink}>
                  Open the sheet ↗
                </a>
              </p>
            ) : sheet === "no_access" ? (
              <>
                <p className="text-sm">Allow the fixes log in Google Drive (only files this app creates).</p>
                <GoogleSignInButton
                  label="Grant access"
                  callbackURL={`/app/accounts/${account.id}`}
                  className={`${buttonPrimary} mt-3 ${smallButton}`}
                />
              </>
            ) : (
              <form action={createSheetAction}>
                <p className="text-sm">
                  {sheet === "missing" ? "The sheet was deleted or moved to the bin." : "No sheet yet."}
                </p>
                <input type="hidden" name="id" value={account.id} />
                <button type="submit" className={`${buttonPrimary} mt-3 ${smallButton}`}>
                  Create a new sheet
                </button>
              </form>
            )}
          </div>
        </div>

        <div className={card}>
          <h2 className="text-lg font-semibold">Remove account</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Disconnects every assistant and deletes this account&apos;s settings and change queue
            here. The fixes-log sheet stays in your Drive.
          </p>
          <form action={removeAccountAction} className="mt-4">
            <input type="hidden" name="id" value={account.id} />
            <button type="submit" className={`${buttonSecondary} ${smallButton}`}>
              Remove {name}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
