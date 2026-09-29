import { oauthProviderClient } from "@better-auth/oauth-provider/client";
import { createAuthClient } from "better-auth/react";

/**
 * oauthProviderClient forwards the signed OAuth query of the current page
 * (/login, /oauth/consent) with every POST, so signing in with Google in
 * the middle of an MCP client's authorization resumes it afterwards.
 */
export const authClient = createAuthClient({ plugins: [oauthProviderClient()] });
