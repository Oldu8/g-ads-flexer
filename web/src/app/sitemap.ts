import type { MetadataRoute } from "next";

import { ALLOW_INDEXING, PUBLIC_PATHS, SITE_URL } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  if (!ALLOW_INDEXING) return [];
  return PUBLIC_PATHS.map((path) => ({ url: `${SITE_URL}${path}` }));
}
