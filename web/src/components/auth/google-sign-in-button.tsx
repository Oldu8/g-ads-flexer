"use client";

import { useState } from "react";

import { authClient } from "@/lib/auth-client";

export function GoogleSignInButton() {
  const [pending, setPending] = useState(false);
  return (
    <button
      type="button"
      disabled={pending}
      onClick={async () => {
        setPending(true);
        await authClient.signIn.social({
          provider: "google",
          callbackURL: "/app",
          errorCallbackURL: "/login?error=1",
        });
      }}
      className="mt-6 w-full rounded-lg bg-mint-400 px-4 py-2.5 font-medium text-ink hover:bg-mint-200 disabled:opacity-60"
    >
      {pending ? "Redirecting to Google…" : "Sign in with Google"}
    </button>
  );
}
