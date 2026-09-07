"""One-off helper: run the installed-app OAuth flow and write credentials to .env.

Usage:
    uv run scripts/get_refresh_token.py path/to/client_secret_....json [path/to/.env]

Opens a browser window, asks you to sign in with the Google account that has
access to the MCC/manager account, and grants the Google Ads API scope.
GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET, and GOOGLE_ADS_REFRESH_TOKEN
are written directly into the target .env file (existing lines replaced
in-place). Secret values are never printed to stdout.
"""

import json
import re
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Fixed scope required by the Google Ads API.
SCOPES = ["https://www.googleapis.com/auth/adwords"]


def set_env_var(env_text: str, key: str, value: str) -> str:
    """Replace `KEY=...` in env_text, or append it if not present."""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", flags=re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(env_text):
        return pattern.sub(line, env_text)
    sep = "" if env_text.endswith("\n") or not env_text else "\n"
    return f"{env_text}{sep}{line}\n"


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print(
            "Usage: uv run scripts/get_refresh_token.py <client_secret.json> [.env path]"
        )
        sys.exit(1)

    client_secrets_path = Path(sys.argv[1])
    env_path = Path(sys.argv[2]) if len(sys.argv) == 3 else Path(".env")

    secrets_data = json.loads(client_secrets_path.read_text())
    installed = secrets_data.get("installed") or secrets_data.get("web") or {}
    client_id = installed.get("client_id")
    client_secret = installed.get("client_secret")
    if not client_id or not client_secret:
        print("Could not find client_id/client_secret in the provided JSON file.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets_path), scopes=SCOPES
    )
    # run_local_server spins up a temporary localhost redirect listener and
    # opens your default browser to the Google consent screen.
    credentials = flow.run_local_server(port=0)

    if not credentials.refresh_token:
        print(
            "No refresh token returned. This usually means the account already "
            "granted consent before; revoke access at https://myaccount.google.com/permissions "
            "for this app and re-run this script."
        )
        sys.exit(1)

    env_text = env_path.read_text() if env_path.exists() else ""
    env_text = set_env_var(env_text, "GOOGLE_ADS_CLIENT_ID", client_id)
    env_text = set_env_var(env_text, "GOOGLE_ADS_CLIENT_SECRET", client_secret)
    env_text = set_env_var(
        env_text, "GOOGLE_ADS_REFRESH_TOKEN", credentials.refresh_token
    )
    env_path.write_text(env_text)

    print(f"\nAuthorization successful. Updated {env_path}:")
    print("  GOOGLE_ADS_CLIENT_ID     [set]")
    print("  GOOGLE_ADS_CLIENT_SECRET [set]")
    print("  GOOGLE_ADS_REFRESH_TOKEN [set]")
    print("\n(No secret values were printed to this terminal.)")


if __name__ == "__main__":
    main()
