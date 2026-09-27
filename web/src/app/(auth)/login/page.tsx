import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { GoogleSignInButton } from "@/components/auth/google-sign-in-button";
import { Logo } from "@/components/logo";
import { getSession } from "@/lib/session";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage(props: PageProps<"/login">) {
  if (await getSession()) redirect("/app");
  const { error } = await props.searchParams;

  return (
    <main className="flex flex-1 items-center justify-center bg-surface px-6">
      <div className="w-full max-w-sm rounded-xl border border-line bg-white p-8">
        <Logo />
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Use the Google account that has access to your Google Ads manager
          account (MCC). Google will ask to allow access to Google Ads.
        </p>
        {error ? (
          <p className="mt-4 rounded-lg bg-tint px-3 py-2 text-sm text-ink">
            Sign-in did not complete. Please try again.
          </p>
        ) : null}
        <GoogleSignInButton />
      </div>
    </main>
  );
}
