#!/usr/bin/env python3
"""Regenerate the source table in SOURCES.md from data/normalized/.

The "Notes" section below the table is prose and stays hand-written —
only the ``| ID | Source | ... |`` table between the two HTML markers
gets replaced. Run this after any script that adds or edits a source
so the docs don't quietly drift from the data, which is a genre of bug
that's no fun to track down six months later.
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_MD = ROOT / "SOURCES.md"

START_MARKER = "<!-- sources-table:start -->"
END_MARKER = "<!-- sources-table:end -->"


def load(name: str) -> list[dict]:
    with (ROOT / "data" / "normalized" / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    sources = load("sources.csv")
    profiles = {p["source_id"]: p for p in load("source_profiles.csv")}
    record_counts: dict[str, int] = {}
    for r in load("source_records.csv"):
        record_counts[r["source_id"]] = record_counts.get(r["source_id"], 0) + 1

    lines = [
        "| ID | Source | Type | Region | Records | Weight | Counts | Link |",
        "|---:|---|---|---:|---:|---:|:---:|---|",
    ]
    for s in sorted(sources, key=lambda s: int(s["source_id"])):
        sid = s["source_id"]
        p = profiles.get(sid, {})
        count = record_counts.get(sid, 0)
        counts_toward = p.get("counts_toward_confidence", "true") == "true"
        # Repo homepage over the raw data URL when there's a choice — a
        # human clicking "upstream" wants the readable page, not a bare
        # JSON file dumped in their browser.
        link = s["upstream_repo"] or s["update_url"] or ""
        lines.append(
            f"| {sid} | {s['name']} | {s['source_type'].replace('_', ' ')} | "
            f"{s['scope_region']} | {count:,} | {p.get('base_weight', '0')} | "
            f"{'yes' if counts_toward else 'no'} | "
            + (f"[upstream]({link})" if link else "")
            + " |"
        )
    table = "\n".join(lines)

    text = SOURCES_MD.read_text(encoding="utf-8")
    if START_MARKER not in text or END_MARKER not in text:
        raise SystemExit(
            f"expected {START_MARKER} / {END_MARKER} markers in SOURCES.md around the table — "
            "add them once (immediately before/after the table) and re-run."
        )
    before, rest = text.split(START_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)
    new_text = f"{before}{START_MARKER}\n{table}\n{END_MARKER}{after}"
    SOURCES_MD.write_text(new_text, encoding="utf-8")
    print(f"SOURCES.md: wrote {len(sources)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
