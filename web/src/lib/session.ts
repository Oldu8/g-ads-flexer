import "server-only";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

/** The signed-in session, or null. Full check against the database. */
export async function getSession() {
  return auth.api.getSession({ headers: await headers() });
}

/** The signed-in session; redirects to /login when there is none. */
export async function requireSession() {
  const session = await getSession();
  if (!session) redirect("/login");
  return session;
}
