import type { Metadata } from "next";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "About" };

/** Written in web track B4. */
export default function Page() {
  return <PagePlaceholder title="About" />;
}
