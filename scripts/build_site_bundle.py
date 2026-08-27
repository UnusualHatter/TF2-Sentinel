#!/usr/bin/env python3
"""Build docs/data/accounts.compact.json, the copy of the database the site loads.

accounts.json stays the public interface: one readable object per account, with
every field a consumer might want. It is also 18 MB, and a browser that has to
parse it and hold 36,000 fifteen-key objects in memory spends most of the page
load doing that and nothing else.

This writes the same rows in a columnar form instead. The repeated parts —
source slugs, flag combinations, confidence tiers, scores — become small
dictionaries that each row refers to by index, and the fields the site never
displays are left out. The result is about a twelfth of the size and parses
into a handful of arrays instead of 36,000 objects.

Run it after export_site_data.py. validate.yml rebuilds it and fails if what
is committed does not match.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DATA_DIR = ROOT / "docs" / "data"
ACCOUNTS_PATH = DOCS_DATA_DIR / "accounts.json"
BUNDLE_PATH = DOCS_DATA_DIR / "accounts.compact.json"

FORMAT_VERSION = 1
ID_PREFIX = "7656119"


class Dictionary:
    """Assigns a stable index to each distinct value, in first-seen order."""

    def __init__(self):
        self.index: dict = {}
        self.values: list = []

    def __call__(self, value):
        found = self.index.get(value)
        if found is None:
            found = self.index[value] = len(self.values)
            self.values.append(value)
        return found


def split_list(value: str) -> list[str]:
    return list(dict.fromkeys(part for part in str(value or "").split(";") if part))


def ordered_slugs(row: dict) -> list[str]:
    """Sources asserting the strongest determination first, then the rest.

    The site used to work this out for every row on every render; the order
    only depends on the stored data, so it is settled once here instead.
    """
    everything = split_list(row.get("all_sources"))
    strongest = [slug for slug in split_list(row.get("strongest_sources")) if slug in everything]
    remaining = [slug for slug in everything if slug not in strongest]
    return strongest + remaining


def build(accounts: list[dict]) -> dict:
    slugs = Dictionary()
    slug_sets = Dictionary()
    flag_sets = Dictionary()
    tiers = Dictionary()
    scores = Dictionary()

    ids, names, tier_col, score_col = [], [], [], []
    groups, evidence, flags_col, primary_col, sources_col = [], [], [], [], []

    for row in accounts:
        steamid64 = str(row.get("steamid64") or "")
        if len(steamid64) != 17 or not steamid64.startswith(ID_PREFIX) or not steamid64.isdigit():
            raise ValueError(f"unexpected SteamID64 in accounts.json: {steamid64!r}")

        ids.append(int(steamid64[len(ID_PREFIX):]))
        names.append(row.get("latest_name") or "")
        tier_col.append(tiers(row.get("confidence_tier") or "unscored"))
        score_col.append(scores(str(row.get("confidence_score") or "")))
        groups.append(int(row.get("independent_source_groups") or 0))
        evidence.append(int(row.get("evidence_count") or 0))
        flags_col.append(flag_sets(tuple(split_list(row.get("flags")))))

        primary = row.get("primary_source") or ""
        primary_col.append(slugs(primary) if primary else -1)
        sources_col.append(slug_sets(tuple(slugs(slug) for slug in ordered_slugs(row))))

    return {
        "version": FORMAT_VERSION,
        "count": len(ids),
        "id_prefix": ID_PREFIX,
        "tiers": tiers.values,
        "scores": scores.values,
        "slugs": slugs.values,
        "source_sets": [list(value) for value in slug_sets.values],
        "flag_sets": [list(value) for value in flag_sets.values],
        "ids": ids,
        "names": names,
        "tier": tier_col,
        "score": score_col,
        "groups": groups,
        "evidence": evidence,
        "flags": flags_col,
        "primary": primary_col,
        "sources": sources_col,
    }


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".bundle-", suffix=".json")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, separators=(",", ":"))
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    accounts_path = Path(argv[0]) if argv else ACCOUNTS_PATH
    bundle_path = Path(argv[1]) if argv and len(argv) > 1 else BUNDLE_PATH

    raw = accounts_path.read_bytes()
    accounts = json.loads(raw.decode("utf-8"))
    if not isinstance(accounts, list):
        print(f"{accounts_path} does not contain a list", file=sys.stderr)
        return 1

    document = build(accounts)
    # Lets validate.yml and anyone debugging a stale deployment tell at a glance
    # whether the bundle was built from the accounts.json sitting next to it.
    document["accounts_digest"] = hashlib.sha256(raw).hexdigest()

    write_json(bundle_path, document)
    print(f"{bundle_path.name}: {document['count']} accounts, "
          f"{len(document['slugs'])} slugs, {len(document['source_sets'])} source combinations, "
          f"{bundle_path.stat().st_size / 1_000_000:.2f} MB "
          f"(accounts.json is {len(raw) / 1_000_000:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
