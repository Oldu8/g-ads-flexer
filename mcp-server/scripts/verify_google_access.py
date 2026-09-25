"""Verify, against the live API, what Google announced on 2026-09-09.

Claims under test (docs/ROADMAP.md, Phase 0 gate):
  C0  The OAuth client belongs to Cloud project 178951272716 (the project
      whose access level now applies to every call).
  C1  Calls work with NO developer-token header at all.
  C2  Calls work with a garbage developer-token header (it is ignored).
  C3  No manager account is needed: an account the identity can access
      directly is queryable without login-customer-id.
  C4  Accounts under a manager are still reachable with login-customer-id.
  C5  Writes are permitted at the project's access level (checked with
      validate_only: nothing is created).
  C6  The SDK path our server uses works (google-ads, as installed).

Run it twice: once as the operator, once as a *second* Google identity that
never had a developer token or an MCC and was only granted access to one ad
account in the Google Ads UI. The second run is the one that proves the
product premise.

Usage:
    uv run scripts/verify_google_access.py --client-secrets client_secret.json --label operator
    uv run scripts/verify_google_access.py --client-secrets client_secret.json --label second-identity
    uv run scripts/verify_google_access.py --client-id <id>.apps.googleusercontent.com --label operator
        (asks for the client secret with hidden input; no JSON file needed)
    uv run scripts/verify_google_access.py --from-env --label operator   # reuse .env credentials

Nothing secret is printed. The report is written to ./tmp/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

API_VERSION = "v25"
BASE = f"https://googleads.googleapis.com/{API_VERSION}"
EXPECTED_PROJECT_NUMBER = "178951272716"
SCOPES = [
    "https://www.googleapis.com/auth/adwords",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
# Error codes that mean "access itself is broken", as opposed to a field
# validation error on our deliberately minimal validate_only payload.
ACCESS_ERROR_TYPES = {
    "authenticationError",
    "authorizationError",
    "headerError",
    "quotaError",
    "accessInvitationError",
}


@dataclass
class Check:
    claim: str
    name: str
    ok: Optional[bool]  # None = skipped / not applicable
    detail: str
    request_id: str = ""
    raw_error: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- credentials


def load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def credentials_from_secrets(path: Path, port: int) -> Tuple[str, str, str]:
    data = json.loads(path.read_text())
    block = data.get("installed") or data.get("web") or {}
    client_id, client_secret = block.get("client_id"), block.get("client_secret")
    if not client_id or not client_secret:
        sys.exit("client_id/client_secret not found in the client-secrets JSON.")
    return browser_consent(client_id, client_secret, port)


def browser_consent(
    client_id: str, client_secret: str, port: int
) -> Tuple[str, str, str]:
    """Installed-app OAuth flow from a bare client id + secret.

    Cloud Console no longer lets you download or view an existing client
    secret, so the JSON file is optional: this builds the same config.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(config, scopes=SCOPES)
    print("Opening the browser. Sign in with the identity you want to test.")
    creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        sys.exit(
            "No refresh token returned. Revoke this app at "
            "https://myaccount.google.com/permissions and re-run."
        )
    return client_id, client_secret, creds.refresh_token


def mint_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        err = resp.json().get("error", resp.text)
        sys.exit(
            f"Token refresh failed: {err}. 'invalid_grant' = refresh token "
            "expired/revoked (Testing-mode apps expire them after 7 days); "
            "'unauthorized_client' = token was issued to a different OAuth client."
        )
    return resp.json()["access_token"]


def token_info(access_token: str) -> Dict[str, Any]:
    resp = requests.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"access_token": access_token},
        timeout=30,
    )
    return resp.json() if resp.status_code == 200 else {}


# ---------------------------------------------------------------- REST calls


def call(
    method: str,
    path: str,
    access_token: str,
    *,
    dev_token: Optional[str] = None,
    login_customer_id: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, Any], str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if dev_token is not None:
        headers["developer-token"] = dev_token
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id
    resp = requests.request(
        method, f"{BASE}/{path}", headers=headers, json=body, timeout=60
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"raw": resp.text[:500]}
    return resp.status_code, payload, resp.headers.get("request-id", "")


def error_codes(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    codes: List[Dict[str, str]] = []
    for detail in payload.get("error", {}).get("details", []):
        for err in detail.get("errors", []):
            codes.append(
                {**err.get("errorCode", {}), "message": err.get("message", "")}
            )
    return codes


def summarize_error(status: int, payload: Dict[str, Any]) -> str:
    codes = error_codes(payload)
    if codes:
        return (
            "; ".join(f"{k}={v}" for c in codes for k, v in c.items() if k != "message")
            + f" ({codes[0].get('message', '')})"
        )
    return f"HTTP {status}: {payload.get('error', {}).get('message', payload)}"


def search(
    access_token: str,
    customer_id: str,
    query: str,
    login_customer_id: Optional[str] = None,
) -> Tuple[int, Dict[str, Any], str]:
    return call(
        "POST",
        f"customers/{customer_id}/googleAds:search",
        access_token,
        login_customer_id=login_customer_id,
        body={"query": query},
    )


# ---------------------------------------------------------------- the checks


def run_checks(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    write_customer: Optional[str],
) -> Tuple[List[Check], Dict[str, Any]]:
    checks: List[Check] = []
    context: Dict[str, Any] = {}

    project = client_id.split("-", 1)[0]
    checks.append(
        Check(
            "C0",
            "OAuth client belongs to the expected Cloud project",
            project == EXPECTED_PROJECT_NUMBER,
            f"client project number {project}, expected {EXPECTED_PROJECT_NUMBER}",
        )
    )

    access_token = mint_access_token(client_id, client_secret, refresh_token)
    info = token_info(access_token)
    context["identity"] = info.get("email", "(email scope not granted)")
    context["granted_scopes"] = info.get("scope", "")
    print(f"Identity: {context['identity']}")

    # C1: no developer-token header.
    status, payload, rid = call(
        "GET", "customers:listAccessibleCustomers", access_token
    )
    accessible = [r.split("/")[-1] for r in payload.get("resourceNames", [])]
    checks.append(
        Check(
            "C1",
            "listAccessibleCustomers without developer-token header",
            status == 200,
            f"{len(accessible)} accessible customer(s)"
            if status == 200
            else summarize_error(status, payload),
            rid,
            {} if status == 200 else payload,
        )
    )
    if status != 200:
        return checks, context

    # C2: garbage developer-token header.
    status, payload, rid = call(
        "GET",
        "customers:listAccessibleCustomers",
        access_token,
        dev_token="INVALID-verify-script",
    )
    checks.append(
        Check(
            "C2",
            "listAccessibleCustomers with a garbage developer-token header",
            status == 200,
            "header ignored" if status == 200 else summarize_error(status, payload),
            rid,
            {} if status == 200 else payload,
        )
    )

    # C3: direct access, no login-customer-id.
    accounts: List[Dict[str, Any]] = []
    for cid in accessible:
        status, payload, rid = search(
            access_token,
            cid,
            "SELECT customer.id, customer.descriptive_name, customer.manager, "
            "customer.test_account, customer.status FROM customer",
        )
        if status == 200 and payload.get("results"):
            c = payload["results"][0]["customer"]
            accounts.append(
                {
                    "customer_id": cid,
                    "name": c.get("descriptiveName", ""),
                    "manager": bool(c.get("manager")),
                    "test_account": bool(c.get("testAccount")),
                    "status": c.get("status", ""),
                    "login_customer_id": None,
                }
            )
            checks.append(
                Check(
                    "C3",
                    f"direct query of {cid}",
                    True,
                    f"{c.get('descriptiveName', '')} manager={bool(c.get('manager'))}",
                    rid,
                )
            )
        elif any(
            c.get("authorizationError") == "CUSTOMER_NOT_ENABLED"
            for c in error_codes(payload)
        ):
            # The account itself is cancelled or never activated; it still
            # shows up in listAccessibleCustomers. Not an access problem.
            checks.append(
                Check(
                    "C3",
                    f"direct query of {cid}",
                    None,
                    "account not enabled (cancelled or never activated) - skipped",
                    rid,
                )
            )
        else:
            checks.append(
                Check(
                    "C3",
                    f"direct query of {cid}",
                    False,
                    summarize_error(status, payload),
                    rid,
                    payload,
                )
            )

    # C4: children of managers via login-customer-id.
    for mgr in [a for a in accounts if a["manager"]]:
        status, payload, rid = search(
            access_token,
            mgr["customer_id"],
            "SELECT customer_client.id, customer_client.descriptive_name, customer_client.manager, "
            "customer_client.status, customer_client.test_account, customer_client.level "
            "FROM customer_client WHERE customer_client.level > 0",
            login_customer_id=mgr["customer_id"],
        )
        if status != 200:
            checks.append(
                Check(
                    "C4",
                    f"customer_client walk under {mgr['customer_id']}",
                    False,
                    summarize_error(status, payload),
                    rid,
                    payload,
                )
            )
            continue
        children = [r["customerClient"] for r in payload.get("results", [])]
        checks.append(
            Check(
                "C4",
                f"customer_client walk under {mgr['customer_id']}",
                True,
                f"{len(children)} descendant(s)",
                rid,
            )
        )
        for child in children:
            if child.get("manager") or child.get("status") != "ENABLED":
                continue
            cid = str(child["id"])
            status, payload, rid = search(
                access_token,
                cid,
                "SELECT customer.id, customer.descriptive_name FROM customer",
                login_customer_id=mgr["customer_id"],
            )
            ok = status == 200
            checks.append(
                Check(
                    "C4",
                    f"query {cid} via manager {mgr['customer_id']}",
                    ok,
                    "ok" if ok else summarize_error(status, payload),
                    rid,
                    {} if ok else payload,
                )
            )
            if ok and not any(a["customer_id"] == cid for a in accounts):
                accounts.append(
                    {
                        "customer_id": cid,
                        "name": child.get("descriptiveName", ""),
                        "manager": False,
                        "test_account": bool(child.get("testAccount")),
                        "status": "ENABLED",
                        "login_customer_id": mgr["customer_id"],
                    }
                )
    context["accounts"] = accounts
    if not any(a["manager"] for a in accounts):
        checks.append(
            Check(
                "C4",
                "manager path",
                None,
                "identity has no manager account - nothing to test (expected for a plain user)",
            )
        )

    # C5: write permission via validate_only (creates nothing).
    target = next(
        (a for a in accounts if a["customer_id"] == write_customer),
        next(
            (a for a in accounts if not a["manager"] and a["status"] == "ENABLED"), None
        ),
    )
    if target is None:
        checks.append(
            Check(
                "C5",
                "validate_only write",
                None,
                "no enabled non-manager account to test on",
            )
        )
    else:
        status, payload, rid = call(
            "POST",
            f"customers/{target['customer_id']}/campaignBudgets:mutate",
            access_token,
            login_customer_id=target["login_customer_id"],
            body={
                "operations": [
                    {
                        "create": {
                            "name": f"verify-validate-only-{datetime.now(timezone.utc):%Y%m%d%H%M%S}",
                            "amountMicros": "10000000",
                            "deliveryMethod": "STANDARD",
                        }
                    }
                ],
                "validateOnly": True,
            },
        )
        if status == 200:
            checks.append(
                Check(
                    "C5",
                    f"validate_only budget create on {target['customer_id']}",
                    True,
                    "write path permitted; nothing was created",
                    rid,
                )
            )
        else:
            codes = error_codes(payload)
            access_broken = any(k in ACCESS_ERROR_TYPES for c in codes for k in c)
            checks.append(
                Check(
                    "C5",
                    f"validate_only budget create on {target['customer_id']}",
                    not access_broken,
                    (
                        "reached validation, rejected on a field (access is fine): "
                        if not access_broken
                        else ""
                    )
                    + summarize_error(status, payload),
                    rid,
                    payload,
                )
            )

    # C6: the SDK path.
    checks.append(sdk_check(client_id, client_secret, refresh_token, accounts))
    return checks, context


def sdk_check(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    accounts: List[Dict[str, Any]],
) -> Check:
    from google.ads.googleads.client import GoogleAdsClient

    sdk = pkg_version("google-ads")
    cfg: Dict[str, Any] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    note = "no developer_token configured"
    try:
        client = GoogleAdsClient.load_from_dict(cfg)
        names = (
            client.get_service("CustomerService", version=API_VERSION)
            .list_accessible_customers()
            .resource_names
        )
        detail = f"{len(names)} accessible; {note}"
        target = next((a for a in accounts if not a["manager"]), None)
        if target:
            if target["login_customer_id"]:
                client.login_customer_id = target["login_customer_id"]
            rows = client.get_service("GoogleAdsService", version=API_VERSION).search(
                customer_id=target["customer_id"],
                query="SELECT customer.id FROM customer",
            )
            detail += f"; search on {target['customer_id']} returned {sum(1 for _ in rows)} row(s)"
        return Check("C6", f"SDK google-ads {sdk}", True, detail)
    except Exception as e:  # noqa: BLE001 - diagnostic script: report, don't crash
        return Check(
            "C6",
            f"SDK google-ads {sdk}",
            False,
            f"{type(e).__name__}: {str(e)[:300]}; {note}",
        )


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--client-secrets",
        type=Path,
        help="OAuth client JSON downloaded from Cloud Console",
    )
    src.add_argument(
        "--client-id",
        help="OAuth client id; the secret is asked for with hidden input",
    )
    src.add_argument(
        "--from-env",
        action="store_true",
        help="use GOOGLE_ADS_CLIENT_ID/SECRET/REFRESH_TOKEN from .env",
    )
    parser.add_argument(
        "--label", default="run", help="identity label for the report file name"
    )
    parser.add_argument(
        "--customer", help="customer id for the validate_only write check"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="loopback port (use 8080 for a 'Web application' OAuth client)",
    )
    parser.add_argument(
        "--write-env",
        type=Path,
        help="also write client id/secret/refresh token into this .env",
    )
    args = parser.parse_args()

    if args.from_env:
        env = {**load_env_file(Path(".env")), **os.environ}
        try:
            client_id, client_secret, refresh_token = (
                env["GOOGLE_ADS_CLIENT_ID"],
                env["GOOGLE_ADS_CLIENT_SECRET"],
                env["GOOGLE_ADS_REFRESH_TOKEN"],
            )
        except KeyError as e:
            sys.exit(f"missing {e} in .env / environment")
    elif args.client_id:
        import getpass

        client_secret = (
            os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
            or getpass.getpass("Client secret (input hidden): ").strip()
        )
        if not client_secret:
            sys.exit("empty client secret")
        client_id, client_secret, refresh_token = browser_consent(
            args.client_id, client_secret, args.port
        )
    else:
        client_id, client_secret, refresh_token = credentials_from_secrets(
            args.client_secrets, args.port
        )

    if args.write_env:
        text = args.write_env.read_text() if args.write_env.exists() else ""
        for key, value in (
            ("GOOGLE_ADS_CLIENT_ID", client_id),
            ("GOOGLE_ADS_CLIENT_SECRET", client_secret),
            ("GOOGLE_ADS_REFRESH_TOKEN", refresh_token),
        ):
            line = f"{key}={value}"
            pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
            text = (
                pattern.sub(line, text)
                if pattern.search(text)
                else text
                + ("" if text.endswith("\n") or not text else "\n")
                + line
                + "\n"
            )
        args.write_env.write_text(text)
        print(f"Credentials written to {args.write_env} (values not printed).")

    checks, context = run_checks(client_id, client_secret, refresh_token, args.customer)

    print(f"\n{'claim':<6}{'result':<8}check / detail")
    for c in checks:
        mark = "SKIP" if c.ok is None else ("PASS" if c.ok else "FAIL")
        print(
            f"{c.claim:<6}{mark:<8}{c.name}\n{'':14}{c.detail}{f'  [request-id {c.request_id}]' if c.request_id else ''}"
        )

    failed = [c for c in checks if c.ok is False]
    print(
        f"\n{'ALL CLAIMS HOLD' if not failed else f'{len(failed)} CHECK(S) FAILED'} for {context.get('identity')}"
    )
    print(
        "Also check by hand: https://console.cloud.google.com/google/ads-apis/overview?project="
        + EXPECTED_PROJECT_NUMBER
    )

    out_dir = Path("tmp")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y-%m-%d}_{args.label}_verify-google-access.json"
    out.write_text(
        json.dumps(
            {
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "api_version": API_VERSION,
                "google_ads_sdk": pkg_version("google-ads"),
                **context,
                "checks": [asdict(c) for c in checks],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"Report: {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
