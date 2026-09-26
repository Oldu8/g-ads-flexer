import type { Metadata } from "next";

import { Logo } from "@/components/logo";

export const metadata: Metadata = { title: "Sign in" };

/** Sign-in page; Google sign-in (with the adwords scope) is wired in web track B1. */
export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center bg-surface px-6">
      <div className="w-full max-w-sm rounded-xl border border-line bg-white p-8">
        <Logo />
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Use the Google account that has access to your Google Ads manager
          account (MCC).
        </p>
        <button
          type="button"
          disabled
          className="mt-6 w-full rounded-lg bg-mint-400 px-4 py-2.5 font-medium text-ink opacity-60"
        >
          Sign in with Google
        </button>
        <p className="mt-3 text-xs text-ink-muted">Sign-in opens soon.</p>
      </div>
    </main>
  );
}
