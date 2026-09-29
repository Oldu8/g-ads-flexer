"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  addAccounts,
  CONTEXT_MAX,
  createSheetFor,
  disconnectClient,
  getAccount,
  getConnection,
  removeAccount,
  setAllowChanges,
  setContext,
  setEnabled,
} from "@/lib/cabinet";
import { discoverAccounts } from "@/lib/google";
import { requireSession } from "@/lib/session";

/**
 * Cabinet mutations. Server actions are reachable by direct POST, so each
 * one re-reads the session and scopes every change to its user.
 */

const field = (form: FormData, name: string) => String(form.get(name) ?? "");
const accountPath = (id: string) => `/app/accounts/${id}`;

export async function saveDiscoveredAction(form: FormData) {
  const { user } = await requireSession();
  const connection = await getConnection(user.id);
  if (!connection) redirect("/app");
  const chosen = new Set(form.getAll("customer").map(String));
  // Only ids from a fresh discovery count: never trust ids from the form alone.
  const { accounts } = await discoverAccounts(connection);
  await addAccounts(
    user.id,
    connection,
    accounts.filter((a) => chosen.has(a.customerId)),
  );
  revalidatePath("/app");
  redirect("/app");
}

export async function setEnabledAction(form: FormData) {
  const { user } = await requireSession();
  const id = field(form, "id");
  await setEnabled(user.id, id, field(form, "enabled") === "true");
  revalidatePath(accountPath(id));
}

export async function setAllowChangesAction(form: FormData) {
  const { user } = await requireSession();
  const id = field(form, "id");
  await setAllowChanges(user.id, id, field(form, "allow") === "true");
  revalidatePath(accountPath(id));
}

export type ContextState = { status: "idle" | "saved" | "too_long" | "error" };

export async function saveContextAction(_prev: ContextState, form: FormData): Promise<ContextState> {
  const { user } = await requireSession();
  const id = field(form, "id");
  const context = field(form, "context").replace(/\r\n/g, "\n").trim();
  if (context.length > CONTEXT_MAX) return { status: "too_long" };
  const ok = await setContext(user.id, id, context);
  revalidatePath(accountPath(id));
  return { status: ok ? "saved" : "error" };
}

export async function createSheetAction(form: FormData) {
  const { user } = await requireSession();
  const id = field(form, "id");
  const [account, connection] = await Promise.all([getAccount(user.id, id), getConnection(user.id)]);
  if (account && connection) await createSheetFor(account, connection);
  revalidatePath(accountPath(id));
}

export async function disconnectClientAction(form: FormData) {
  const { user } = await requireSession();
  const id = field(form, "id");
  await disconnectClient(user.id, id, field(form, "clientId"));
  revalidatePath(accountPath(id));
}

export async function removeAccountAction(form: FormData) {
  const { user } = await requireSession();
  await removeAccount(user.id, field(form, "id"));
  revalidatePath("/app");
  redirect("/app");
}
