import { oauthProviderOpenIdConfigMetadata } from "@better-auth/oauth-provider";

import { auth } from "@/lib/auth";

/** OIDC discovery at the origin root and in the path-inserted form. */
export const GET = oauthProviderOpenIdConfigMetadata(auth);
