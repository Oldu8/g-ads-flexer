"use client";

import { useActionState, useState } from "react";

import { type ContextState, saveContextAction } from "@/app/(cabinet)/app/actions";
import { buttonPrimary } from "@/components/ui";

const MAX = 2000;

const messages: Record<ContextState["status"], string> = {
  idle: "",
  saved: "Saved.",
  too_long: `Too long: at most ${MAX} characters.`,
  error: "Could not save. Reload the page and try again.",
};

export function ContextForm({ id, initial }: { id: string; initial: string }) {
  const [state, action, pending] = useActionState<ContextState, FormData>(saveContextAction, { status: "idle" });
  const [length, setLength] = useState(initial.length);
  return (
    <form action={action} className="mt-4">
      <input type="hidden" name="id" value={id} />
      <textarea
        name="context"
        defaultValue={initial}
        maxLength={MAX}
        rows={6}
        onChange={(e) => setLength(e.target.value.length)}
        placeholder="What the business sells, margins, what matters (e.g. “pawnshop marketplace, ~10% margin, ROAS ≠ profit”)."
        className="w-full rounded-lg border border-line-strong p-3 text-sm focus-visible:outline-2 focus-visible:outline-accent"
      />
      <div className="mt-2 flex items-center justify-between gap-4">
        <span className="text-xs text-ink-muted">
          {length} / {MAX}
          {messages[state.status] ? ` · ${messages[state.status]}` : ""}
        </span>
        <button type="submit" disabled={pending} className={`${buttonPrimary} px-4 py-2 text-sm`}>
          {pending ? "Saving…" : "Save context"}
        </button>
      </div>
    </form>
  );
}
