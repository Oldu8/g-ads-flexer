"use client";

import { useState } from "react";

import { buttonPrimary } from "@/components/ui";
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
      className={`${buttonPrimary} mt-6 w-full`}
    >
      {pending ? "Redirecting to Google…" : "Sign in with Google"}
    </button>
  );
}
