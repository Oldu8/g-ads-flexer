/**
 * End-to-end check of the MCP OAuth flow against a local dev server and the
 * app_dev schema, without a browser (spec account-connection, tasks 3.5/4.4).
 *
 * Seeds two throwaway users with sessions and ad accounts, then as user A:
 * registers a public client (DCR), authorizes with PKCE for A's account URL,
 * consents, exchanges the code, verifies the JWT against the JWKS, refreshes;
 * and checks the refusals: B's account, A's disabled account, a refresh after
 * A switches the account off, B's account page. Everything seeded is deleted
 * at the end. Tokens are never printed.
 *
 *   npm run dev   # in another terminal
 *   node --env-file=.env.local scripts/oauth-dev-check.mjs
 */
import { createHash, createHmac, randomBytes, randomUUID } from "node:crypto";

import { createRemoteJWKSet, decodeJwt, decodeProtectedHeader, jwtVerify } from "jose";
import postgres from "postgres";

const BASE = process.env.CHECK_BASE_URL ?? "http://localhost:3000";
const MCP = (process.env.MCP_PUBLIC_URL ?? "").replace(/\/+$/, "");
if (process.env.DB_SCHEMA !== "app_dev" || !/^http:\/\/(localhost|127\.0\.0\.1)/.test(BASE)) {
  console.error("Refusing to run: only against a local server and DB_SCHEMA=app_dev.");
  process.exit(2);
}

const sql = postgres(process.env.DATABASE_URL, { max: 2, onnotice: () => {} });
const results = [];
const check = (name, ok, detail = "") => {
  results.push(ok);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
};

const b64url = (buf) => Buffer.from(buf).toString("base64url");
const slug = () => {
  const abc = "abcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from(randomBytes(12), (b) => abc[b % 36]).join("");
};

async function seedUser(label, accounts) {
  const [user] = await sql`
    insert into users (name, email, email_verified)
    values (${`check ${label}`}, ${`oauth-check-${label}-${randomUUID()}@example.invalid`}, true)
    returning id`;
  const token = b64url(randomBytes(24));
  await sql`
    insert into sessions (user_id, token, expires_at)
    values (${user.id}, ${token}, now() + interval '1 hour')`;
  const [conn] = await sql`
    insert into google_connections (user_id, account_id, provider_id, scope)
    values (${user.id}, ${`check-${randomUUID()}`}, 'google', 'openid')
    returning id`;
  const rows = [];
  for (const [i, enabled] of accounts.entries()) {
    const s = slug();
    const [row] = await sql`
      insert into ad_accounts (user_id, google_connection_id, customer_id, display_name, enabled, mcp_slug)
      values (${user.id}, ${conn.id}, ${String(9000000000 + Math.floor(Math.random() * 99999999))},
              ${`Check ${label}${i}`}, ${enabled}, ${s})
      returning id, mcp_slug`;
    await sql`
      insert into oauth_resources (identifier, name, disabled, created_at, updated_at)
      values (${`${MCP}/${s}`}, ${`check ${label}${i}`}, ${!enabled}, now(), now())`;
    rows.push({ id: row.id, url: `${MCP}/${s}` });
  }
  // better-call signed cookie: value.base64(hmac-sha256(secret, value)), URI-encoded
  const sig = createHmac("sha256", process.env.BETTER_AUTH_SECRET).update(token).digest("base64");
  return { id: user.id, cookie: `better-auth.session_token=${encodeURIComponent(`${token}.${sig}`)}`, accounts: rows };
}

const REDIRECT = "http://localhost:53682/callback";
const verifier = b64url(randomBytes(32));
const challenge = b64url(createHash("sha256").update(verifier).digest());

async function authorize(cookie, clientId, resource) {
  const q = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: REDIRECT,
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: "st",
    resource,
  });
  // Headers of a browser navigation: Better Auth answers fetches with JSON.
  const res = await fetch(`${BASE}/api/auth/oauth2/authorize?${q}`, {
    headers: { cookie, accept: "text/html", "sec-fetch-mode": "navigate" },
    redirect: "manual",
  });
  const location = res.headers.get("location") ?? (await res.json().catch(() => ({}))).url ?? "";
  return new URL(location, BASE);
}

async function consent(cookie, consentUrl) {
  const res = await fetch(`${BASE}/api/auth/oauth2/consent`, {
    method: "POST",
    headers: { cookie, "content-type": "application/json", origin: BASE },
    body: JSON.stringify({ accept: true, oauth_query: consentUrl.search.slice(1) }),
  });
  return { status: res.status, body: await res.json().catch(() => ({})) };
}

async function token(params) {
  const res = await fetch(`${BASE}/api/auth/oauth2/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(params),
  });
  return { status: res.status, body: await res.json().catch(() => ({})) };
}

let clientId;
const seeded = [];
try {
  const a = await seedUser("a", [true, false]);
  const b = await seedUser("b", [true]);
  seeded.push(a, b);
  const [aOn, aOff] = a.accounts;
  const [bOn] = b.accounts;

  // Dynamic client registration, unauthenticated, public client (as Claude does it).
  const reg = await fetch(`${BASE}/api/auth/oauth2/register`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      client_name: "adsmigo oauth check",
      redirect_uris: [REDIRECT],
      token_endpoint_auth_method: "none",
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
    }),
  });
  const client = await reg.json();
  clientId = client.client_id;
  check("dynamic client registration", reg.status < 300 && Boolean(clientId), `status ${reg.status}`);

  const consentUrl = await authorize(a.cookie, clientId, aOn.url);
  check("authorize sends a new client to /oauth/consent", consentUrl.pathname === "/oauth/consent", consentUrl.pathname);

  const page = await fetch(`${BASE}/oauth/consent${consentUrl.search}`, { headers: { cookie: a.cookie } });
  const html = await page.text();
  check("consent page names the client and the account", html.includes("adsmigo oauth check") && html.includes("Check a0"));

  const accepted = await consent(a.cookie, consentUrl);
  const codeUrl = new URL(accepted.body.url ?? accepted.body.redirect_uri ?? "http://x/");
  const code = codeUrl.searchParams.get("code");
  check("consent returns a code to the client", accepted.status === 200 && Boolean(code), `status ${accepted.status}`);

  const exchanged = await token({
    grant_type: "authorization_code",
    code,
    redirect_uri: REDIRECT,
    client_id: clientId,
    code_verifier: verifier,
    resource: aOn.url,
  });
  const access = exchanged.body.access_token ?? "";
  check("code exchange returns an access and a refresh token",
    exchanged.status === 200 && access.split(".").length === 3 && Boolean(exchanged.body.refresh_token),
    `status ${exchanged.status}${exchanged.body.error ? ` ${exchanged.body.error}` : ""}`);

  if (access) {
    const header = decodeProtectedHeader(access);
    const claims = decodeJwt(access);
    console.log("      claims:", JSON.stringify({ ...claims, sub: claims.sub === a.id ? "<user a>" : claims.sub }));
    const meta = await (await fetch(`${BASE}/.well-known/oauth-authorization-server`)).json();
    const { payload } = await jwtVerify(access, createRemoteJWKSet(new URL(meta.jwks_uri)), {
      issuer: meta.issuer,
      audience: aOn.url,
    });
    const mcpAudiences = [payload.aud].flat().filter((aud) => String(aud).startsWith(`${MCP}/`));
    check("JWT is ES256, verifies against the JWKS, one MCP aud = account URL, sub = user",
      header.alg === "ES256" && payload.sub === a.id && mcpAudiences.length === 1 && mcpAudiences[0] === aOn.url);
    check("access token lives at most one hour", Number(payload.exp) - Number(payload.iat) <= 3600,
      `${Number(payload.exp) - Number(payload.iat)} s`);
  }

  const refreshed = await token({
    grant_type: "refresh_token",
    refresh_token: exchanged.body.refresh_token ?? "",
    client_id: clientId,
    resource: aOn.url,
  });
  check("refresh works while the account is on", refreshed.status === 200 && Boolean(refreshed.body.access_token),
    `status ${refreshed.status}`);

  // Refusals.
  const foreignConsent = await authorize(a.cookie, clientId, bOn.url);
  const foreign = foreignConsent.pathname === "/oauth/consent" ? await consent(a.cookie, foreignConsent) : null;
  check("another user's account: consent refused, no code",
    foreignConsent.searchParams.get("error") === "invalid_target" ||
      (foreign !== null && foreign.status >= 400 && !String(foreign.body.url ?? "").includes("code=")),
    foreign ? `consent status ${foreign.status}` : `authorize → ${foreignConsent.searchParams.get("error")}`);

  const disabled = await authorize(a.cookie, clientId, aOff.url);
  const disabledConsent = disabled.pathname === "/oauth/consent" ? await consent(a.cookie, disabled) : null;
  check("own disabled account refused",
    disabled.searchParams.get("error") !== null || (disabledConsent !== null && disabledConsent.status >= 400),
    disabled.searchParams.get("error") ?? `consent status ${disabledConsent?.status}`);

  await sql`update ad_accounts set enabled = false where id = ${aOn.id}`;
  await sql`update oauth_resources set disabled = true where identifier = ${aOn.url}`;
  const afterOff = await token({
    grant_type: "refresh_token",
    refresh_token: refreshed.body.refresh_token ?? "",
    client_id: clientId,
    resource: aOn.url,
  });
  check("refresh refused after the account is switched off", afterOff.status >= 400, `status ${afterOff.status}`);

  const foreignPage = await fetch(`${BASE}/app/accounts/${bOn.id}`, { headers: { cookie: a.cookie } });
  check("cabinet: another user's account page is 404", foreignPage.status === 404, `status ${foreignPage.status}`);
  const ownPage = await fetch(`${BASE}/app/accounts/${aOn.id}`, { headers: { cookie: a.cookie } });
  const ownHtml = await ownPage.text();
  check("cabinet: own account page shows its MCP URL", ownPage.status === 200 && ownHtml.includes(aOn.url),
    `status ${ownPage.status}`);
} catch (error) {
  check("script ran to the end", false, error instanceof Error ? error.message : String(error));
} finally {
  for (const u of seeded) {
    for (const acc of u.accounts) await sql`delete from oauth_resources where identifier = ${acc.url}`;
    await sql`delete from users where id = ${u.id}`;
  }
  if (clientId) await sql`delete from oauth_clients where client_id = ${clientId}`;
  await sql.end();
}

const failed = results.filter((ok) => !ok).length;
console.log(failed ? `\n${failed} check(s) failed` : "\nall checks passed");
process.exit(failed ? 1 : 0);
