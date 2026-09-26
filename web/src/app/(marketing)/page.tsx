import Link from "next/link";

import { SITE_TAGLINE } from "@/lib/site";

/** Placeholder landing; the real one is web track B3 (design from Stitch). */
export default function HomePage() {
  return (
    <section className="mx-auto max-w-5xl px-6 py-28">
      <p className="inline-flex rounded-full bg-mint-50 px-3 py-1 text-sm text-mint-700">
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
        <Link
          href="/login"
          className="rounded-lg bg-mint-400 px-5 py-2.5 font-medium text-ink hover:bg-mint-200"
        >
          Sign in with Google
        </Link>
      </div>
    </section>
  );
}
