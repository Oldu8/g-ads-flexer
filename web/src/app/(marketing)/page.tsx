import Link from "next/link";

import { badge, buttonPrimary } from "@/components/ui";
import { SITE_TAGLINE } from "@/lib/site";

/** Placeholder landing; the real one is web track B3 (design from Stitch). */
export default function HomePage() {
  return (
    <section className="mx-auto max-w-5xl px-6 py-28">
      <p className={badge}>
        Private beta
      </p>
      <h1 className="mt-6 max-w-3xl text-5xl font-semibold tracking-tight sm:text-6xl">
        {SITE_TAGLINE}
      </h1>
      <p className="mt-6 max-w-2xl text-lg text-ink-muted">
        Connect your MCC, pick accounts, work with Claude or ChatGPT. Every change
        is previewed, approved and logged.
      </p>
      <div className="mt-10 flex gap-3">
        <Link href="/login" className={buttonPrimary}>
          Sign in with Google
        </Link>
      </div>
    </section>
  );
}
