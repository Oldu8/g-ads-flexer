import Link from "next/link";

import { Logo } from "@/components/logo";

export function SiteHeader() {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
        <Logo />
        <nav className="flex items-center gap-6 text-sm text-ink-muted">
          <Link href="/blog" className="hover:text-ink">
            Blog
          </Link>
          <Link href="/about" className="hover:text-ink">
            About
          </Link>
          <Link
            href="/login"
            className="rounded-lg border border-line-strong px-3 py-1.5 text-ink transition-colors hover:bg-surface"
          >
            Sign in
          </Link>
        </nav>
      </div>
    </header>
  );
}
