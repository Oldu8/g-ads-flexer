"""Reusable ad-hoc GAQL query runner against the real Google Ads account.

Usage:
    uv run scripts/gaql.py <customer_id> "<GAQL query>" [--json]

Examples:
    uv run scripts/gaql.py 5690318342 "SELECT campaign.id, campaign.name FROM campaign WHERE campaign.status = 'ENABLED'"
    uv run scripts/gaql.py 5690318342 "SELECT metrics.cost_micros FROM customer WHERE segments.date DURING THIS_MONTH" --json

Uses the same GOOGLE_ADS_* credentials from .env as the MCP server itself.
customer_id is required and takes no dashes (e.g. 5690318342, not 569-031-8342).
"""

import json
import sys
from pathlib import Path

# Windows consoles default to a legacy codepage (e.g. cp1252) that can't
# encode Cyrillic/etc. Reconfigure stdout to UTF-8 so query results with
# non-ASCII text (ad copy, keywords, ...) don't crash on print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sdk_client import GoogleAdsSdkClient  # noqa: E402
from src.utils import load_dotenv, serialize_proto_message  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]

    if len(args) != 2:
        print(__doc__)
        sys.exit(1)

    customer_id, query = args
    customer_id = customer_id.replace("-", "")

    load_dotenv()
    sdk = GoogleAdsSdkClient()
    ga_service = sdk.client.get_service("GoogleAdsService", version="v25")

    rows = ga_service.search(customer_id=customer_id, query=query)

    if as_json:
        results = [serialize_proto_message(row) for row in rows]
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        count = 0
        for row in rows:
            print(row)
            count += 1
        print(f"\n({count} row{'s' if count != 1 else ''})")


if __name__ == "__main__":
    main()
