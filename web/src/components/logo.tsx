import Link from "next/link";

import { SITE_NAME } from "@/lib/site";

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <span aria-hidden className="size-2.5 rounded-full bg-mint-400" />
      {SITE_NAME}
    </Link>
  );
}
