import { oauthProviderAuthServerMetadata } from "@better-auth/oauth-provider";

import { auth } from "@/lib/auth";

/**
 * RFC 8414 metadata at the origin root and in the path-inserted form for
 * the issuer `<origin>/api/auth`: MCP clients (Claude) look for it here.
 */
export const GET = oauthProviderAuthServerMetadata(auth);
