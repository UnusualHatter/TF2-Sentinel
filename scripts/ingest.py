#!/usr/bin/env python3
"""Refresh the sources that can be re-read automatically.

Reads the source catalog straight out of data/normalized/sources.csv, which is
the source of truth, and re-fetches every tf2bd-style playerlist that has an
update URL. Those are single JSON files published at a stable address, so
refetching them unattended is cheap and safe.

The other source types are left alone:

  sourcebans        26 community websites, each a slightly different HTML
                    layout that breaks without warning. Scraping them from a
                    scheduled job is what produced the truncated imports this
                    database already carries. Community bans are refreshed in
                    bulk through fetch_steamhistory_bans.py instead.
  everything else   imported by hand; see scripts/README.md.

Run recompute_confidence.py, export_site_data.py, build_site_bundle.py and
generate_sources_md.py afterwards, or the published files still describe the
previous import.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_CSV = ROOT / "data" / "normalized" / "sources.csv"

REFRESHABLE = {"tf2bd_playerlist"}


def load_sources(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", type=Path, default=SOURCES_CSV)
    parser.add_argument("--only", help="refresh a single source by slug")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be refreshed without fetching")
    args = parser.parse_args(argv)

    sources = load_sources(args.sources)
    stats = Counter()
    failures: list[str] = []

    for source in sources:
        if args.only and source["slug"] != args.only:
            continue
        if source["source_type"] not in REFRESHABLE:
            stats["not_refreshable"] += 1
            continue
        url = (source.get("update_url") or "").strip()
        if not url:
            stats["no_update_url"] += 1
            continue

        print(f"[{source['source_id']}] {source['slug']}")
        if args.dry_run:
            print(f"    would fetch {url}")
            stats["would_refresh"] += 1
            continue

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ingest_tf2bd.py"),
             "--source-id", source["source_id"], "--url", url],
            check=False)
        if result.returncode == 0:
            stats["refreshed"] += 1
        else:
            stats["failed"] += 1
            failures.append(source["slug"])

    print("\n" + " · ".join(f"{k}: {v}" for k, v in sorted(stats.items())))
    if failures:
        # A source that would not download is worth seeing in the log, but it
        # is not a reason to fail the run and leave the rest unrefreshed.
        print("could not refresh: " + ", ".join(failures), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
