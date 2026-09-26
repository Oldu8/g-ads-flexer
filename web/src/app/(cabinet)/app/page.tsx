import type { Metadata } from "next";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Your accounts" };

/** Cabinet home; protected in web track B1, built in web track B2. */
export default function CabinetPage() {
  return <PagePlaceholder title="Your ad accounts" />;
}
