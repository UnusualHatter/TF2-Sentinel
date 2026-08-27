#!/usr/bin/env python3
"""Rebuild confidence.csv, account_summary.csv and summary.json from source data.

Everything this script produces is derived — accounts.csv, source_records.csv,
flags.csv, aliases.csv and evidence.csv are the inputs of record; these three
files are just a materialized view over them, kept as flat files so the
website doesn't need a database sitting behind it. Run this after any script
that touches flags/aliases/evidence (e.g. merge_sourcebans.py); until it runs,
the published scores still describe the previous import. The workflow in
.github/workflows/validate.yml fails the build if the committed output does
not match what this produces.

The confidence formula mirrors db/init/005_confidence_views.sql exactly —
see that file for the authoritative version. account_summary's status
priority mirrors db/init/002_views.sql's v_account_summary.

steam_persona_name / avatar_url / avatar_full_url are carried forward from
the existing confidence.csv unchanged: this script has no way to look them
up itself (see docs/app.js for the client-side avatar enrichment that
populates them for previously-unseen accounts).
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "normalized"

# Kept as strings so they become exact Decimals; 0.45 as a binary float is
# not exactly 0.45, and these feed a score compared against the SQL view's
# NUMERIC arithmetic.
MULTIPLIER = {
    "cheater": Decimal("1.00"),
    "bot": Decimal("1.00"),
    "exploiter": Decimal("0.70"),
    "suspicious": Decimal("0.45"),
    "association": Decimal("0.10"),
    "cheater_supporter": Decimal("0.10"),
    "server_ban": Decimal("0.00"),
    "clear": Decimal("0.00"),
    "owner": Decimal("0.00"),
}
DEFAULT_MULTIPLIER = Decimal("0.20")
MAX_CONTRIBUTION = Decimal("99.5")


def load(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    with (DATA_DIR / name).open("w", newline="", encoding="utf-8") as f:
        # csv defaults to \r\n regardless of how the file was opened, which
        # would rewrite every line of every file. Match the existing CSVs.
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def contribution(base_weight: str, flag: str) -> Decimal:
    """One source's contribution to an account's score, as a percentage."""
    weight = Decimal(base_weight) * MULTIPLIER.get(flag.lower(), DEFAULT_MULTIPLIER)
    return min(MAX_CONTRIBUTION, weight)


def round_score(value: Decimal, ndigits: int) -> str:
    # Half away from zero, which is what PostgreSQL's numeric round() does.
    # Python's built-in round() is half-to-even and disagrees on exact .x5
    # values, which do occur here (a lone weight-5 'suspicious' flag scores
    # 2.25). Verified against a live PostgreSQL run of the view.
    quantum = Decimal(1).scaleb(-ndigits)
    return str(value.quantize(quantum, rounding=ROUND_HALF_UP))


def main() -> int:
    accounts = load("accounts.csv")
    flags = load("flags.csv")
    source_records = load("source_records.csv")
    aliases = load("aliases.csv")
    evidence = load("evidence.csv")
    sources = load("sources.csv")
    source_profiles = load("source_profiles.csv")
    old_confidence = {r["steamid64"]: r for r in load("confidence.csv")}

    source_name = {s["source_id"]: s["name"] for s in sources}
    source_slug = {s["source_id"]: s["slug"] for s in sources}
    profile = {p["source_id"]: p for p in source_profiles}

    # ---- group inputs by steamid64 ----
    flags_by_account: dict[str, list[dict]] = defaultdict(list)
    for f in flags:
        flags_by_account[f["steamid64"]].append(f)

    records_by_account: dict[str, list[dict]] = defaultdict(list)
    for r in source_records:
        records_by_account[r["steamid64"]].append(r)

    evidence_count_by_account: dict[str, int] = defaultdict(int)
    for e in evidence:
        evidence_count_by_account[e["steamid64"]] += 1

    latest_alias_by_account: dict[str, dict] = {}
    for a in sorted(aliases, key=lambda a: (a["observed_at"] or "", int(a["alias_id"]))):
        latest_alias_by_account[a["steamid64"]] = a  # last write wins == latest

    # ---- per-account confidence ----
    confidence_fields = [
        "steamid64", "steam3", "latest_name", "steam_persona_name", "steam_profile_url",
        "steamhistory_url", "avatar_url", "avatar_full_url", "confidence_score",
        "confidence_tier", "independent_source_groups", "source_count", "raw_source_signals",
        "evidence_count", "flags", "primary_source", "primary_source_name",
        "strongest_sources", "strongest_source_names", "all_sources", "all_source_names",
    ]
    summary_fields = [
        "steamid64", "steam3", "aggregate_status", "source_count", "flags", "evidence_count",
        "latest_name", "latest_name_observed_at", "first_observed_at", "last_observed_at",
    ]

    confidence_rows = []
    summary_rows = []
    tier_counts: dict[str, int] = defaultdict(int)
    server_ban_flags = 0
    with_avatar = 0
    with_persona = 0

    for acc in accounts:
        steamid64 = acc["steamid64"]
        acc_flags = flags_by_account.get(steamid64, [])
        active_flags = [f for f in acc_flags if f.get("active", "true") == "true"]

        # -- contributions, independence groups, confidence score --
        best_per_group: dict[str, tuple[Decimal, str, str]] = {}  # group -> (contribution, source_id, flag)
        for f in active_flags:
            sp = profile.get(f["source_id"])
            if not sp or sp["counts_toward_confidence"] != "true":
                continue
            c = contribution(sp["base_weight"], f["flag"])
            group = sp["independence_group"]
            cur = best_per_group.get(group)
            if cur is None or c > cur[0] or (c == cur[0] and int(f["source_id"]) < int(cur[1])):
                best_per_group[group] = (c, f["source_id"], f["flag"])

        if best_per_group:
            # Noisy-OR: 1 - prod(1 - c/100), i.e. the chance that at least one
            # independent source group is right. The SQL view writes this as
            # exp(sum(ln(...))) only because SQL has no product aggregate;
            # multiplying directly is the same thing and avoids ln/exp
            # rounding error in the last digit.
            survival = Decimal(1)
            for c, _, _ in best_per_group.values():
                survival *= 1 - c / Decimal(100)
            raw_score = Decimal(100) * (1 - survival)
            score_str = round_score(raw_score, 1)
        else:
            score_str = "0.0"
        score = Decimal(score_str)

        if score >= 95:
            tier = "very_high"
        elif score >= 80:
            tier = "high"
        elif score >= 60:
            tier = "medium"
        elif score >= 30:
            tier = "low"
        elif score > 0:
            tier = "very_low"
        else:
            tier = "unscored"
        tier_counts[tier] += 1

        # -- primary / strongest source: overall max contribution --
        best_overall = max((v[0] for v in best_per_group.values()), default=Decimal(0))
        strongest_ids = sorted(
            {v[1] for v in best_per_group.values() if v[0] == best_overall and best_overall > 0},
            key=int,
        )
        primary_id = strongest_ids[0] if strongest_ids else ""

        # -- all_sources: every source that has a record for this account,
        # ranked by its own best contribution (non-counting/no-flag sources sort last) --
        acc_records = records_by_account.get(steamid64, [])
        source_best_contribution = {v[1]: v[0] for v in best_per_group.values()}
        all_ids = sorted(
            dict.fromkeys(r["source_id"] for r in acc_records),
            key=lambda sid: (-source_best_contribution.get(sid, Decimal(-1)), int(sid)),
        )

        alias = latest_alias_by_account.get(steamid64)
        old = old_confidence.get(steamid64, {})

        confidence_rows.append({
            "steamid64": steamid64,
            "steam3": acc["steam3"],
            "latest_name": alias["player_name"] if alias else "",
            "steam_persona_name": old.get("steam_persona_name", ""),
            "steam_profile_url": f"https://steamcommunity.com/profiles/{steamid64}/",
            "steamhistory_url": f"https://steamhistory.net/id/{steamid64}",
            "avatar_url": old.get("avatar_url", ""),
            "avatar_full_url": old.get("avatar_full_url", ""),
            "confidence_score": score_str,
            "confidence_tier": tier,
            "independent_source_groups": str(len(best_per_group)),
            "source_count": str(len(all_ids)),
            "raw_source_signals": str(len(acc_flags)),
            "evidence_count": str(evidence_count_by_account.get(steamid64, 0)),
            "flags": ";".join(sorted({f["flag"] for f in active_flags})),
            # primary/strongest/all_sources are exported as slugs, not numeric
            # source_ids — same convention docs/data/accounts.json uses, since
            # that's what a reader without this repo's CSVs open can still
            # make sense of.
            "primary_source": source_slug.get(primary_id, ""),
            "primary_source_name": source_name.get(primary_id, ""),
            "strongest_sources": ";".join(source_slug.get(sid, sid) for sid in strongest_ids),
            "strongest_source_names": ";".join(source_name.get(sid, "") for sid in strongest_ids),
            "all_sources": ";".join(source_slug.get(sid, sid) for sid in all_ids),
            "all_source_names": ";".join(source_name.get(sid, "") for sid in all_ids),
        })

        if old.get("avatar_url"):
            with_avatar += 1
        if old.get("steam_persona_name"):
            with_persona += 1

        # -- account_summary.csv (mirrors v_account_summary) --
        flag_values = {f["flag"] for f in active_flags}
        if "cheater" in flag_values:
            status = "flagged_cheater"
        elif "suspicious" in flag_values:
            status = "suspicious"
        elif "exploiter" in flag_values:
            status = "flagged_exploiter"
        else:
            status = "other"
        server_ban_flags += sum(1 for f in active_flags if f["flag"] == "server_ban")

        summary_rows.append({
            "steamid64": steamid64,
            "steam3": acc["steam3"],
            "aggregate_status": status,
            "source_count": str(len({f["source_id"] for f in active_flags})),
            "flags": ";".join(sorted(flag_values)),
            "evidence_count": str(evidence_count_by_account.get(steamid64, 0)),
            "latest_name": alias["player_name"] if alias else "",
            "latest_name_observed_at": alias["observed_at"] if alias else "",
            "first_observed_at": acc["first_observed_at"],
            "last_observed_at": acc["last_observed_at"],
        })

    save("confidence.csv", confidence_fields, confidence_rows)
    save("account_summary.csv", summary_fields, summary_rows)

    data_bearing = len({r["source_id"] for r in source_records})
    summary = {
        "unique_accounts": len(accounts),
        "source_records": len(source_records),
        "flags": len(flags),
        "evidence_rows": len(evidence),
        "aliases": len(aliases),
        "server_bans": server_ban_flags,
        "registered_sources": len(sources),
        "data_bearing_sources": data_bearing,
        "accounts_with_avatar": with_avatar,
        "accounts_with_persona": with_persona,
        "confidence_tiers": dict(sorted(tier_counts.items())),
        "generated_at": datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M:%S-03:00"),
    }
    (DATA_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"accounts: {len(accounts)}")
    print(f"confidence tiers: {dict(sorted(tier_counts.items()))}")
    print("wrote confidence.csv, account_summary.csv, summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
