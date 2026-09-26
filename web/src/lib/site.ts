/** Site-wide constants. The product name is a working name (ROADMAP, Q9). */
export const SITE_NAME = "adsmigo";

export const SITE_TAGLINE =
  "Google Ads, managed in chat. Nothing changes without your yes.";

/** Public origin, e.g. https://ads.vtrata.com. Used for metadata and sitemap. */
export const SITE_URL = (process.env.SITE_URL ?? "http://localhost:3000").replace(
  /\/$/,
  "",
);

/**
 * Search engines are kept out until the product has its final name and
 * domain (ROADMAP 0.2a): indexing a temporary domain would have to be
 * redirected later. Set ALLOW_INDEXING=true to open the public pages.
 */
export const ALLOW_INDEXING = process.env.ALLOW_INDEXING === "true";

/** Public pages that belong in the sitemap once indexing is allowed. */
export const PUBLIC_PATHS = ["/", "/blog", "/about", "/privacy", "/terms"] as const;

export const FOOTER_LINKS = [
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
  { href: "/about", label: "About" },
  { href: "/blog", label: "Blog" },
] as const;
