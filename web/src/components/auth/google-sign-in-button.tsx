"use client";

import { useState } from "react";

import { buttonPrimary } from "@/components/ui";
import { authClient } from "@/lib/auth-client";

/**
 * Google sign-in. Also used to re-run the grant (e.g. to add Drive access):
 * Better Auth updates the existing connection. On /login during an MCP
 * client's authorization, the signed OAuth query rides along and the flow
 * resumes after Google.
 */
export function GoogleSignInButton({
  label = "Sign in with Google",
  callbackURL = "/app",
  className = `${buttonPrimary} mt-6 w-full`,
}: {
  label?: string;
  callbackURL?: string;
  className?: string;
}) {
  const [pending, setPending] = useState(false);
  return (
    <button
      type="button"
      disabled={pending}
      onClick={async () => {
        setPending(true);
        await authClient.signIn.social({
          provider: "google",
          callbackURL,
          errorCallbackURL: "/login?error=1",
        });
      }}
      className={className}
    >
      {pending ? "Redirecting to Google…" : label}
    </button>
  );
}
