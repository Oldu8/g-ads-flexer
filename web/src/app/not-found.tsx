import Link from "next/link";

import { textLink } from "@/components/ui";

export default function NotFound() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
      <p className="text-sm text-primary">404</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Page not found</h1>
      <Link href="/" className={`${textLink} mt-6`}>
        Back to home
      </Link>
    </main>
  );
}
