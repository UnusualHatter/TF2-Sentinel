#!/usr/bin/env python3
"""Regenerate docs/data/{accounts,sources,meta}.json from data/normalized/.

The website is static and dependency-free by design (see docs/app.js) — no
build step, no server, just these JSON files fetched straight into the
browser. Run this after recompute_confidence.py so the site catches up
with whatever the CSVs now say. Doesn't touch docs/data/servers.json;
nothing here changes the South America server reference data.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "normalized"
DOCS_DATA_DIR = ROOT / "docs" / "data"

# Hardcoded rather than strftime("%B"), which would render in whatever locale
# the machine running the sync happens to use. The site is in English.
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def load(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, data) -> None:
    # Compact rather than indented, matching the existing files: accounts.json
    # is a multi-megabyte download for every visitor and is never read by hand.
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build_accounts() -> list[dict]:
    rows = []
    for r in load("confidence.csv"):
        rows.append({
            "steamid64": r["steamid64"],
            "steam3": r["steam3"],
            "latest_name": r["latest_name"],
            "steam_persona_name": r["steam_persona_name"],
            "avatar_url": r["avatar_url"],
            "confidence_score": r["confidence_score"],
            "confidence_tier": r["confidence_tier"],
            "independent_source_groups": int(r["independent_source_groups"]),
            "source_count": int(r["source_count"]),
            "raw_source_signals": int(r["raw_source_signals"]),
            "evidence_count": int(r["evidence_count"]),
            "flags": r["flags"],
            "primary_source": r["primary_source"],
            "strongest_sources": r["strongest_sources"],
            "all_sources": r["all_sources"],
        })
    return rows


def build_sources() -> list[dict]:
    profiles = {p["source_id"]: p for p in load("source_profiles.csv")}
    seed_counts: dict[str, int] = {}
    for rec in load("source_records.csv"):
        seed_counts[rec["source_id"]] = seed_counts.get(rec["source_id"], 0) + 1

    rows = []
    for s in load("sources.csv"):
        p = profiles.get(s["source_id"], {})
        rows.append({
            "source_id": s["source_id"],
            "slug": s["slug"],
            "name": s["name"],
            "short_name": s["name"].split(" — ")[0],
            "source_type": s["source_type"],
            "upstream_repo": s["upstream_repo"],
            "update_url": s["update_url"],
            "authors": s["authors"],
            "scope_region": s["scope_region"],
            "description": s["description"],
            "source_file": s["source_file"],
            "base_weight": p.get("base_weight", ""),
            "evidence_class": p.get("evidence_class", ""),
            "independence_group": p.get("independence_group", ""),
            "counts_toward_confidence": p.get("counts_toward_confidence", ""),
            "is_mirror": p.get("is_mirror", ""),
            "assessment_method": p.get("assessment_method", ""),
            "last_verified": p.get("last_verified", ""),
            "notes": p.get("notes", ""),
            "seed_record_count": seed_counts.get(s["source_id"], 0),
        })
    return rows


def build_meta(summary: dict) -> dict:
    generated_at = summary["generated_at"]
    day = date.fromisoformat(generated_at[:10])
    display = f"{MONTHS[day.month - 1]} {day.day}, {day.year}"
    # servers.json is not rebuilt here: it only changes when someone edits
    # data/reference/south_america_servers.csv by hand, which is not part of
    # this pipeline. Count whatever is already published.
    servers_tracked = len(json.loads((DOCS_DATA_DIR / "servers.json").read_text(encoding="utf-8")))
    return {
        "last_database_update": day.isoformat(),
        "last_database_update_display": display,
        "generated_at": generated_at,
        "timezone": "America/Sao_Paulo",
        "unique_accounts": summary["unique_accounts"],
        "source_records": summary["source_records"],
        "registered_sources": summary["registered_sources"],
        "data_bearing_sources": summary["data_bearing_sources"],
        "servers_tracked": servers_tracked,
    }


def main() -> int:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    accounts = build_accounts()
    write_json(DOCS_DATA_DIR / "accounts.json", accounts)
    print(f"accounts.json: {len(accounts)} rows")

    sources = build_sources()
    write_json(DOCS_DATA_DIR / "sources.json", sources)
    print(f"sources.json: {len(sources)} rows")

    summary = json.loads((DATA_DIR / "summary.json").read_text(encoding="utf-8"))
    meta = build_meta(summary)
    write_json(DOCS_DATA_DIR / "meta.json", meta)
    print(f"meta.json: snapshot dated {meta['last_database_update']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
