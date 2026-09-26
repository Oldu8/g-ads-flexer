import type { Metadata } from "next";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Blog" };

/** Blog index; built in web track B6 from articles stored in the database. */
export default function BlogPage() {
  return <PagePlaceholder title="Blog" />;
}
