#!/usr/bin/env python3
"""Merge parsed SourceBans rows (from fetch_sourcebans.py) into data/normalized/.

Updates accounts.csv, source_records.csv, flags.csv, aliases.csv and
evidence.csv in place. Safe to re-run for the same source: records are
deduplicated by content hash, so a repeat run adds nothing new.

    python scripts/merge_sourcebans.py --source-id 92 --records /tmp/furrypound.json

The source must already have a row in sources.csv / source_profiles.csv
(register it there first — see SOURCES.md for the existing convention).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.classify import classify_reason  # noqa: E402
from lib.dateparse import parse_to_iso  # noqa: E402
from lib.sourcebans import resolve_steamid64  # noqa: E402
from lib.steamid import account_id, to_steam3  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "normalized"

# Placeholder text some skins print when a SourceBans install has nothing to
# show for the player's name — not an actual alias worth recording. Nobody
# is out there legitimately going by "no nickname present".
_JUNK_NAMES = {"", "no nickname present", "bot", "unnamed"}


def load_csv(name: str) -> tuple[list[str], list[dict]]:
    path = DATA_DIR / name
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def save_csv(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    path = DATA_DIR / name
    with path.open("w", newline="", encoding="utf-8") as f:
        # csv defaults to \r\n regardless of how the file was opened, which
        # would rewrite every line of every file. Match the existing CSVs.
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def record_hash(source_id: str, raw_steam_id: str, reason: str, date_iso: str | None) -> str:
    key = f"{source_id}|{raw_steam_id}|{reason}|{date_iso or ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-id", required=True, help="source_id from sources.csv, e.g. 92.")
    ap.add_argument("--records", required=True, help="JSON file produced by fetch_sourcebans.py.")
    ap.add_argument("--dry-run", action="store_true", help="Report what would change without writing anything.")
    args = ap.parse_args()

    source_id = args.source_id
    parsed_rows = json.loads(Path(args.records).read_text(encoding="utf-8"))

    _, sources = load_csv("sources.csv")
    source = next((s for s in sources if s["source_id"] == source_id), None)
    if source is None:
        print(f"error: source_id {source_id} has no row in sources.csv — register it first.", file=sys.stderr)
        return 1
    source_short_name = source["name"].split(" — ")[0]

    acc_fields, accounts = load_csv("accounts.csv")
    accounts_by_id = {a["steamid64"]: a for a in accounts}

    rec_fields, records = load_csv("source_records.csv")
    existing_hashes = {r["record_hash"] for r in records}
    next_record_id = max((int(r["source_record_id"]) for r in records), default=0) + 1
    next_record_index = max(
        (int(r["record_index"]) for r in records if r["source_id"] == source_id), default=-1
    ) + 1

    flag_fields, flags = load_csv("flags.csv")
    flags_by_key = {(f["steamid64"], f["source_id"], f["flag"]): f for f in flags}
    next_flag_id = max((int(f["flag_id"]) for f in flags), default=0) + 1

    alias_fields, aliases = load_csv("aliases.csv")
    existing_alias_keys = {(a["steamid64"], a["source_id"], a["player_name"]) for a in aliases}
    next_alias_id = max((int(a["alias_id"]) for a in aliases), default=0) + 1

    ev_fields, evidence = load_csv("evidence.csv")
    existing_evidence_keys = {(e["steamid64"], e["source_id"], e["content"]) for e in evidence}
    next_evidence_id = max((int(e["evidence_id"]) for e in evidence), default=0) + 1

    stats = {"skipped_no_steamid": 0, "skipped_duplicate": 0, "accounts_new": 0,
             "records_added": 0, "flags_added": 0, "flags_reactivated": 0,
             "aliases_added": 0, "evidence_added": 0}
    flag_breakdown: dict[str, int] = {}

    for row in parsed_rows:
        steamid64 = resolve_steamid64(row)
        if steamid64 is None:
            stats["skipped_no_steamid"] += 1
            continue
        steamid64_s = str(steamid64)

        raw_steam_id = row.get("steam2") or steamid64_s
        reason = (row.get("reason") or "").strip()
        date_iso = parse_to_iso(row.get("date_text") or row.get("date_iso"))
        name = (row.get("name") or "").strip()
        # Only some skins expose whether the ban is still in force. When they
        # don't (active is None), assume it is — an expired ban that we score
        # anyway is a smaller error than dropping a live one.
        is_active = row.get("active") is not False

        rhash = record_hash(source_id, raw_steam_id, reason, date_iso)
        if rhash in existing_hashes:
            stats["skipped_duplicate"] += 1
            continue
        existing_hashes.add(rhash)

        # accounts.csv
        account = accounts_by_id.get(steamid64_s)
        if account is None:
            account = {
                "steamid64": steamid64_s,
                "account_id": str(account_id(steamid64)),
                "steam3": to_steam3(steamid64),
                "first_observed_at": date_iso or "",
                "last_observed_at": date_iso or "",
            }
            accounts_by_id[steamid64_s] = account
            accounts.append(account)
            stats["accounts_new"] += 1
        elif date_iso:
            if not account["first_observed_at"] or date_iso < account["first_observed_at"]:
                account["first_observed_at"] = date_iso
            if not account["last_observed_at"] or date_iso > account["last_observed_at"]:
                account["last_observed_at"] = date_iso

        # source_records.csv
        raw_record = {
            "steam2": row.get("steam2", ""),
            "player_name": name,
            "reason": reason,
            "date_iso": date_iso or "",
            "admin": row.get("admin", ""),
            "steamid64": steamid64_s,
            "active": is_active,
        }
        records.append({
            "source_record_id": str(next_record_id),
            "source_id": source_id,
            "steamid64": steamid64_s,
            "raw_steam_id": raw_steam_id,
            "record_index": str(next_record_index),
            "normalization_note": "",
            "record_hash": rhash,
            "raw_record": json.dumps(raw_record, ensure_ascii=False),
        })
        next_record_id += 1
        next_record_index += 1
        stats["records_added"] += 1

        # flags.csv. The schema keeps one row per (steamid64, source_id, flag),
        # so several bans from the same source collapse into one flag — which
        # counts as active if *any* of them is still in force.
        flag_value = classify_reason(reason)
        flag_key = (steamid64_s, source_id, flag_value)
        existing_flag = flags_by_key.get(flag_key)
        if existing_flag is None:
            flag_row = {
                "flag_id": str(next_flag_id),
                "steamid64": steamid64_s,
                "source_id": source_id,
                "flag": flag_value,
                "review_status": "imported",
                "active": "true" if is_active else "false",
                "observed_at": date_iso or "",
            }
            flags_by_key[flag_key] = flag_row
            flags.append(flag_row)
            next_flag_id += 1
            stats["flags_added"] += 1
            flag_breakdown[flag_value] = flag_breakdown.get(flag_value, 0) + 1
        elif is_active and existing_flag["active"] != "true":
            existing_flag["active"] = "true"
            existing_flag["observed_at"] = date_iso or existing_flag["observed_at"]
            stats["flags_reactivated"] += 1

        # aliases.csv
        if name and name.lower() not in _JUNK_NAMES:
            alias_key = (steamid64_s, source_id, name)
            if alias_key not in existing_alias_keys:
                existing_alias_keys.add(alias_key)
                aliases.append({
                    "alias_id": str(next_alias_id),
                    "steamid64": steamid64_s,
                    "source_id": source_id,
                    "player_name": name,
                    "observed_at": date_iso or "",
                })
                next_alias_id += 1
                stats["aliases_added"] += 1

        # evidence.csv
        if reason:
            content = f"{source_short_name}: {reason}"
            evidence_key = (steamid64_s, source_id, content)
            if evidence_key not in existing_evidence_keys:
                existing_evidence_keys.add(evidence_key)
                evidence.append({
                    "evidence_id": str(next_evidence_id),
                    "steamid64": steamid64_s,
                    "source_id": source_id,
                    "evidence_type": "source_note",
                    "content": content,
                    "observed_at": date_iso or "",
                })
                next_evidence_id += 1
                stats["evidence_added"] += 1

    print(f"source {source_id} ({source['name']}):", file=sys.stderr)
    for k, v in stats.items():
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"  flags by type: {flag_breakdown}", file=sys.stderr)

    if args.dry_run:
        print("dry run — nothing written.", file=sys.stderr)
        return 0

    save_csv("accounts.csv", acc_fields, accounts)
    save_csv("source_records.csv", rec_fields, records)
    save_csv("flags.csv", flag_fields, flags)
    save_csv("aliases.csv", alias_fields, aliases)
    save_csv("evidence.csv", ev_fields, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
