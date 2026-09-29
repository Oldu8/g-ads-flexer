/**
 * Live check of the MCP OAuth flow against a deployed cabinet, the way
 * Claude Code does it (spec account-connection, task 5.4): registers a
 * public loopback client, prints the authorization URL for you to open in
 * your browser, catches the redirect on localhost, exchanges the code with
 * PKCE, verifies the JWT against the JWKS and prints its claims. Tokens are
 * never printed.
 *
 *   node scripts/oauth-smoke.mjs https://ads.vtrata.com https://ads-mcp.vtrata.com/mcp/<slug>
 *
 * The registered client stays (named "adsmigo oauth smoke"); disconnect it
 * on the account page afterwards.
 */
import { createHash, randomBytes } from "node:crypto";
import { createServer } from "node:http";

import { createRemoteJWKSet, decodeProtectedHeader, jwtVerify } from "jose";

const [base, resource] = process.argv.slice(2);
if (!base || !resource) {
  console.error("usage: node scripts/oauth-smoke.mjs <cabinet origin> <account MCP URL>");
  process.exit(2);
}

const PORT = 53682;
const REDIRECT = `http://localhost:${PORT}/callback`;
const b64url = (buf) => Buffer.from(buf).toString("base64url");
const verifier = b64url(randomBytes(32));
const state = b64url(randomBytes(12));

const meta = await (await fetch(new URL("/.well-known/oauth-authorization-server", base))).json();
console.log(`issuer: ${meta.issuer}`);

const reg = await fetch(meta.registration_endpoint, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ client_name: "adsmigo oauth smoke", redirect_uris: [REDIRECT], token_endpoint_auth_method: "none" }),
});
const client = await reg.json();
if (!client.client_id) throw new Error(`registration failed: ${reg.status} ${JSON.stringify(client)}`);
console.log(`registered client ${client.client_id} (${reg.status})`);

const authorizeUrl = new URL(meta.authorization_endpoint);
authorizeUrl.search = new URLSearchParams({
  response_type: "code",
  client_id: client.client_id,
  redirect_uri: REDIRECT,
  code_challenge: b64url(createHash("sha256").update(verifier).digest()),
  code_challenge_method: "S256",
  state,
  resource,
}).toString();
console.log(`\nOpen in your browser (signed in or not):\n\n${authorizeUrl}\n`);

const callback = await new Promise((resolve) => {
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", REDIRECT);
    if (url.pathname !== "/callback") return res.writeHead(404).end();
    res.writeHead(200, { "content-type": "text/plain" }).end("Done. You can close this tab.");
    server.close();
    resolve(url.searchParams);
  }).listen(PORT, "localhost");
});

if (callback.get("error")) {
  console.log(`authorization ended with error: ${callback.get("error")} — ${callback.get("error_description")}`);
  process.exit(1);
}
if (callback.get("state") !== state) throw new Error("state mismatch");

const res = await fetch(meta.token_endpoint, {
  method: "POST",
  headers: { "content-type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({
    grant_type: "authorization_code",
    code: callback.get("code") ?? "",
    redirect_uri: REDIRECT,
    client_id: client.client_id,
    code_verifier: verifier,
    resource,
  }),
});
const tokens = await res.json();
if (!tokens.access_token) {
  console.log(`token exchange failed: ${res.status} ${tokens.error} ${tokens.error_description ?? ""}`);
  process.exit(1);
}
const { payload } = await jwtVerify(tokens.access_token, createRemoteJWKSet(new URL(meta.jwks_uri)), {
  issuer: meta.issuer,
  audience: resource,
});
console.log(`alg: ${decodeProtectedHeader(tokens.access_token).alg}, refresh token: ${Boolean(tokens.refresh_token)}`);
console.log("claims:", JSON.stringify(payload, null, 2));
console.log(`lifetime: ${Number(payload.exp) - Number(payload.iat)} s`);
