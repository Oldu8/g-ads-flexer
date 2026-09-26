"""Write the real `tools/list` payload of a tool profile to a file.

    uv run scripts/dump_tools_list.py --profile manager --out tests/golden/tools_list_manager.json
    uv run scripts/dump_tools_list.py --profile read_only --out tests/golden/tools_list_read_only.json
    uv run scripts/dump_tools_list.py --profile all            # print the size only

No credentials needed: the server is built without its lifespan.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.surface import largest_tools, payload_size, render_tools_list  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", type=Path, help="write the payload here")
    args = parser.parse_args()

    payload = asyncio.run(render_tools_list(args.profile))
    size = payload_size(payload)
    print(
        f"{args.profile}: {len(payload)} tools, {size} chars (~{size // 4} tokens); "
        f"largest: {', '.join(largest_tools(payload))}"
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
