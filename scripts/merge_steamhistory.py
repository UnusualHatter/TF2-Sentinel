#!/usr/bin/env python3
"""Add SteamHistory ban lookups to the database.

Takes the JSON written by fetch_steamhistory_bans.py and turns it into
source_records, flags, aliases and evidence.

Which community a record belongs to is decided in
data/reference/steamhistory_servers.csv, not here, and not at runtime:

  map       the community is already a registered source. The records attach
            to that source, so they inherit its independence group and cannot
            corroborate its own bans a second time.
  register  a TF2 community with no source of its own yet. One gets created,
            weighted below the communities whose ban list was read directly,
            because this arrives through an aggregator.
  skip      not TF2, or not identifiable. Left out.

A server that is not in that table is reported and skipped. Classifying a
community is a judgement call, and guessing at one would put unrelated bans
into a TF2 cheating database.

    python3 scripts/merge_steamhistory.py --records /tmp/steamhistory.json --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.classify import classify_reason  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "normalized"
SERVERS_PATH = ROOT / "data" / "reference" / "steamhistory_servers.csv"

SOURCE_TYPE = "sourcebans"
AGGREGATOR = "steamhistory"
UPSTREAM = "https://steamhistory.net/"
UPDATE_URL = "https://steamhistory.net/api/sourcebans"


def load_csv(name: str) -> tuple[list[str], list[dict]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def save_csv(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    with (DATA_DIR / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def record_hash(source_id: str, raw_steam_id: str, reason: str, date_iso: str) -> str:
    key = f"{source_id}|{raw_steam_id}|{reason}|{date_iso}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def to_iso(epoch: int) -> str:
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return ""


def load_decisions(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return {row["server"]: row for row in csv.DictReader(f) if row.get("server")}


def next_id(rows: list[dict], field: str) -> int:
    return max((int(r[field]) for r in rows if r.get(field, "").isdigit()), default=0) + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--records", type=Path, required=True,
                        help="JSON written by fetch_steamhistory_bans.py")
    parser.add_argument("--servers", type=Path, default=SERVERS_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing anything")
    args = parser.parse_args(argv)

    payload = json.loads(args.records.read_text(encoding="utf-8"))
    incoming = payload.get("records") or []
    if not incoming:
        print("no records to merge", file=sys.stderr)
        return 1
    decisions = load_decisions(args.servers)

    src_fields, sources = load_csv("sources.csv")
    prof_fields, profiles = load_csv("source_profiles.csv")
    acc_fields, accounts = load_csv("accounts.csv")
    rec_fields, records = load_csv("source_records.csv")
    flag_fields, flags = load_csv("flags.csv")
    alias_fields, aliases = load_csv("aliases.csv")
    ev_fields, evidence = load_csv("evidence.csv")

    source_by_slug = {s["slug"]: s for s in sources}
    accounts_by_id = {a["steamid64"]: a for a in accounts}
    existing_hashes = {r["record_hash"] for r in records}
    flags_by_key = {(f["steamid64"], f["source_id"], f["flag"]): f for f in flags}
    alias_keys = {(a["steamid64"], a["source_id"], a["player_name"]) for a in aliases}
    evidence_keys = {(e["steamid64"], e["source_id"], e["content"]) for e in evidence}

    next_source_id = next_id(sources, "source_id")
    next_record_id = next_id(records, "source_record_id")
    next_record_index = next_id(records, "record_index")
    next_flag_id = next_id(flags, "flag_id")
    next_alias_id = next_id(aliases, "alias_id")
    next_evidence_id = next_id(evidence, "evidence_id")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = Counter()
    unclassified: Counter = Counter()
    created_sources: list[str] = []

    def register(server: str, decision: dict) -> dict:
        """Create a source for a community, the first time a record needs one.

        Created on demand rather than up front: a source with no records still
        shows up in the catalog and in the published counts, which overstates
        what the database actually holds.
        """
        nonlocal next_source_id
        slug = decision["source_slug"]
        source = {
            "source_id": str(next_source_id), "slug": slug, "name": decision["name"],
            "source_type": SOURCE_TYPE, "upstream_repo": UPSTREAM, "update_url": UPDATE_URL,
            "authors": "", "scope_region": decision["scope_region"] or "global",
            "description": (f"Community server bans issued by {server}, read through the "
                            f"SteamHistory aggregator rather than from the community's own "
                            f"ban list."),
            "source_file": "",
        }
        sources.append(source)
        source_by_slug[slug] = source
        profiles.append({
            "source_id": str(next_source_id), "base_weight": decision["base_weight"] or "78",
            "evidence_class": "strong",
            "independence_group": decision["independence_group"] or slug,
            "counts_toward_confidence": "true", "is_mirror": "false",
            "assessment_method": "community-ban-via-aggregator", "last_verified": today,
            "notes": decision["notes"],
        })
        created_sources.append(f"{next_source_id} {slug}")
        next_source_id += 1
        return source

    for record in incoming:
        server = record.get("server", "")
        decision = decisions.get(server)
        if decision is None:
            unclassified[server] += 1
            stats["skipped_unclassified"] += 1
            continue
        if decision["decision"] == "skip":
            stats["skipped_by_policy"] += 1
            continue

        source = source_by_slug.get(decision["source_slug"])
        if source is None and decision["decision"] == "register" and decision["source_slug"]:
            source = register(server, decision)
        if source is None:
            stats["skipped_unknown_source"] += 1
            continue
        source_id = source["source_id"]

        steamid64 = record["steamid64"]
        reason = record.get("reason", "")
        date_iso = to_iso(record.get("banned_at", 0))
        rhash = record_hash(source_id, steamid64, reason, date_iso)
        if rhash in existing_hashes:
            stats["skipped_duplicate"] += 1
            continue
        existing_hashes.add(rhash)

        account = accounts_by_id.get(steamid64)
        if account is None:
            # Every account looked up came from this database, so a new one here
            # means the lookup file is out of step with accounts.csv.
            stats["skipped_unknown_account"] += 1
            continue
        if date_iso:
            if not account["first_observed_at"] or date_iso < account["first_observed_at"]:
                account["first_observed_at"] = date_iso
            if not account["last_observed_at"] or date_iso > account["last_observed_at"]:
                account["last_observed_at"] = date_iso

        records.append({
            "source_record_id": str(next_record_id), "source_id": source_id,
            "steamid64": steamid64, "raw_steam_id": steamid64,
            "record_index": str(next_record_index), "normalization_note": f"via {AGGREGATOR}",
            "record_hash": rhash,
            "raw_record": json.dumps({
                "player_name": record.get("name", ""), "reason": reason,
                "unban_reason": record.get("unban_reason", ""), "date_iso": date_iso,
                "unbanned_iso": to_iso(record.get("unbanned_at", 0)),
                "state": record.get("state", ""), "active": bool(record.get("active")),
                "server": server, "steamid64": steamid64, "via": AGGREGATOR,
            }, ensure_ascii=False),
        })
        next_record_id += 1
        next_record_index += 1
        stats["records_added"] += 1

        # One flag row per (account, source, flag); it is active if any of that
        # community's bans on the account is still in force. SteamHistory says
        # so explicitly, which the scraped lists mostly do not.
        flag_value = classify_reason(reason)
        stats[f"flag_{flag_value}"] += 1
        key = (steamid64, source_id, flag_value)
        existing = flags_by_key.get(key)
        if existing is None:
            row = {"flag_id": str(next_flag_id), "steamid64": steamid64, "source_id": source_id,
                   "flag": flag_value, "review_status": "imported",
                   "active": "true" if record.get("active") else "false",
                   "observed_at": date_iso}
            flags.append(row)
            flags_by_key[key] = row
            next_flag_id += 1
            stats["flags_added"] += 1
        elif record.get("active") and existing["active"] != "true":
            existing["active"] = "true"
            stats["flags_reactivated"] += 1

        name = (record.get("name") or "").strip()
        if name and (steamid64, source_id, name) not in alias_keys:
            aliases.append({"alias_id": str(next_alias_id), "steamid64": steamid64,
                            "source_id": source_id, "player_name": name,
                            "observed_at": date_iso})
            alias_keys.add((steamid64, source_id, name))
            next_alias_id += 1
            stats["aliases_added"] += 1

        if reason:
            content = f"[{server} ban] {reason}"
            if (steamid64, source_id, content) not in evidence_keys:
                evidence.append({"evidence_id": str(next_evidence_id), "steamid64": steamid64,
                                 "source_id": source_id, "evidence_type": "source_note",
                                 "content": content, "observed_at": date_iso})
                evidence_keys.add((steamid64, source_id, content))
                next_evidence_id += 1
                stats["evidence_added"] += 1

    print(f"records in file      : {len(incoming)}")
    for label in ("records_added", "flags_added", "flags_reactivated", "aliases_added",
                  "evidence_added", "skipped_duplicate", "skipped_by_policy",
                  "skipped_unclassified", "skipped_unknown_account", "skipped_unknown_source"):
        if stats[label]:
            print(f"{label:21}: {stats[label]}")
    breakdown = {k[5:]: v for k, v in stats.items() if k.startswith("flag_")}
    if breakdown:
        print(f"flag breakdown       : {breakdown}")
    if created_sources:
        print(f"sources created      : {len(created_sources)}")
        for line in created_sources:
            print(f"    {line}")
    if unclassified:
        print("servers missing from the decision table (skipped):")
        for server, count in unclassified.most_common():
            print(f"    {server}: {count}")

    if args.dry_run:
        print("\ndry run: nothing was written")
        return 0

    save_csv("sources.csv", src_fields, sources)
    save_csv("source_profiles.csv", prof_fields, profiles)
    save_csv("accounts.csv", acc_fields, accounts)
    save_csv("source_records.csv", rec_fields, records)
    save_csv("flags.csv", flag_fields, flags)
    save_csv("aliases.csv", alias_fields, aliases)
    save_csv("evidence.csv", ev_fields, evidence)
    print("\nwrote data/normalized/. Now run recompute_confidence.py, export_site_data.py, "
          "build_site_bundle.py and generate_sources_md.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
