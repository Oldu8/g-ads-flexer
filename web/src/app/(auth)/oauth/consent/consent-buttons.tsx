"use client";

import { useState } from "react";

import { buttonPrimary, buttonSecondary } from "@/components/ui";
import { authClient } from "@/lib/auth-client";

/** Allow / Deny; the client plugin forwards this page's signed OAuth query. */
export function ConsentButtons({ canAllow }: { canAllow: boolean }) {
  const [pending, setPending] = useState<"allow" | "deny" | null>(null);
  const [failed, setFailed] = useState(false);

  async function decide(accept: boolean) {
    setPending(accept ? "allow" : "deny");
    setFailed(false);
    const { data, error } = await authClient.oauth2.consent({ accept });
    const url = (data as { url?: string; redirect_uri?: string } | null)?.url ??
      (data as { redirect_uri?: string } | null)?.redirect_uri;
    if (error || !url) {
      setPending(null);
      setFailed(true);
      return;
    }
    window.location.href = url;
  }

  return (
    <div className="mt-8">
      {failed ? (
        <p className="mb-4 rounded-lg bg-tint px-3 py-2 text-sm text-ink">
          Something went wrong. Start the connection again from your AI assistant.
        </p>
      ) : null}
      <div className="flex gap-3">
        {canAllow ? (
          <button
            type="button"
            disabled={pending !== null}
            onClick={() => decide(true)}
            className={`${buttonPrimary} flex-1`}
          >
            {pending === "allow" ? "Connecting…" : "Allow"}
          </button>
        ) : null}
        <button
          type="button"
          disabled={pending !== null}
          onClick={() => decide(false)}
          className={`${buttonSecondary} flex-1`}
        >
          {pending === "deny" ? "Cancelling…" : canAllow ? "Deny" : "Cancel"}
        </button>
      </div>
    </div>
  );
}
