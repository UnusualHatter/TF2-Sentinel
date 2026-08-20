#!/usr/bin/env python3
"""Fetch a SourceBans ban list and dump the parsed rows as JSON.

This only fetches and parses — it doesn't touch data/normalized/. Run it
once per source, review the output, then feed it to merge_sourcebans.py.

Examples:

    python scripts/fetch_sourcebans.py \\
        --url "https://bans.example.tf/index.php?p=banlist" \\
        --out /tmp/example.json

    # A reskin that paginates with an offset query param instead of a
    # page number (seen on at least one community's customized skin):
    python scripts/fetch_sourcebans.py \\
        --url "https://bans.example.tf/bans" \\
        --page-param page2 --page-start 25 --page-step 25 \\
        --out /tmp/example.json

Pulls are capped at --pages requests and stop early once a page adds no
new rows, which in practice means "however many recent pages there
are, up to the cap" rather than a community's full historical archive.
That matches how the rest of the SourceBans sources in this project are
synced — see the "recent-window sync" note in SOURCES.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.sourcebans import parse  # noqa: E402

# Several of these installs reject the default "Python-urllib/3.x" agent
# with a 403. The pages are public and this makes no request a browser
# would not make; the rate limiting below is what keeps it well behaved.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def row_key(row: dict) -> tuple:
    return (
        row.get("steam2") or row.get("steamid64"),
        row.get("reason"),
        row.get("date_text") or row.get("date_iso"),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="First-page URL (with p=banlist already in the query string).")
    ap.add_argument("--out", required=True, help="Where to write the parsed rows as a JSON array.")
    ap.add_argument("--pages", type=int, default=30, help="Max page requests (default: 30).")
    ap.add_argument("--page-param", default="page", help="Pagination query param name (default: page).")
    ap.add_argument("--page-start", type=int, default=2, help="Value of --page-param on the second request (default: 2).")
    ap.add_argument("--page-step", type=int, default=1, help="Increment of --page-param per subsequent request (default: 1).")
    # These are small community-run servers. The delay is courtesy, not a
    # technical requirement; leave it alone unless you have a reason.
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds to sleep between requests (default: 1.5).")
    ap.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds (default: 20).")
    args = ap.parse_args()

    rows: list[dict] = []
    seen: set[tuple] = set()

    for i in range(max(1, args.pages)):
        if i == 0:
            page_url = args.url
        else:
            page_value = args.page_start + args.page_step * (i - 1)
            sep = "&" if "?" in args.url else "?"
            page_url = f"{args.url}{sep}{args.page_param}={page_value}"

        try:
            html = fetch(page_url, args.timeout)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"page {i + 1}: fetch failed ({exc}), stopping", file=sys.stderr)
            break

        page_rows = parse(html)
        new_count = 0
        for row in page_rows:
            key = row_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            new_count += 1

        print(f"page {i + 1}: {len(page_rows)} rows, {new_count} new (total {len(rows)})", file=sys.stderr)

        # A page that returns nothing, or nothing we have not already seen,
        # means the pagination has run out (some skins repeat the last page
        # forever rather than 404).
        if not page_rows or (i > 0 and not new_count):
            break
        time.sleep(args.delay)

    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
