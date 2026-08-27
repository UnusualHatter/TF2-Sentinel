#!/usr/bin/env python3
"""Check that docs/data/profiles.json is something the website can read.

The file is written by a scheduled workflow talking to an external API, so it
is the one generated file that is not reproducible from what is committed.
This is what stands in for the diff check the other generated files get.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import profiles  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROFILES_PATH = ROOT / "docs" / "data" / "profiles.json"
ACCOUNTS_PATH = ROOT / "docs" / "data" / "accounts.json"

HASH_RE = re.compile(r"^[0-9a-f]{40}$")
# A Steam Web API key is 32 uppercase hex characters. Persona names are
# excluded from this scan: players do pick 32-digit names, and one of them
# would otherwise fail the build.
KEY_RE = re.compile(r"\b(?=[0-9A-F]*[A-F])[0-9A-F]{32}\b")


def check(path: Path, accounts_path: Path) -> tuple[list[str], list[str]]:
    """Returns (problems, notes). Only problems fail the build."""
    problems: list[str] = []
    notes: list[str] = []
    raw = json.loads(path.read_text(encoding="utf-8"))

    scanned = json.dumps({k: v for k, v in raw.items() if k != "names"})
    if KEY_RE.search(scanned):
        problems.append("contains something shaped like a Steam Web API key")

    for field in ("version", "generated_at", "count", "avatar_base", "avatar_size"):
        if field not in raw:
            problems.append(f"missing {field!r}")
    if problems:
        return problems, notes

    store = profiles.decode(raw)

    if raw["count"] != len(store):
        problems.append(f"count says {raw['count']} but there are {len(store)} entries")
    if not str(raw["avatar_base"]).startswith("https://"):
        problems.append("avatar_base is not an https URL")

    ids = raw["ids"]
    if ids != sorted(ids):
        problems.append("ids are not sorted; the site looks entries up by binary search")
    if len(set(ids)) != len(ids):
        problems.append("ids contain duplicates")

    for suffix, entry in store.items():
        steamid64 = profiles.steamid64_of(suffix)
        if profiles.suffix_of(steamid64) is None:
            problems.append(f"{suffix} is not a usable SteamID64")
            break
        if entry["hash"] != profiles.NO_AVATAR and not HASH_RE.match(entry["hash"]):
            problems.append(f"{steamid64} has a malformed avatar hash")
            break
        if entry["state"] not in (0, 1, 2, 3):
            problems.append(f"{steamid64} has an unknown state {entry['state']}")
            break
        if entry["fetched"] < 0:
            problems.append(f"{steamid64} has a negative fetch day")
            break

    if accounts_path.exists():
        accounts = json.loads(accounts_path.read_text(encoding="utf-8"))
        known = {profiles.suffix_of(row.get("steamid64")) for row in accounts if isinstance(row, dict)}
        stray = [s for s in store if s not in known]
        if stray:
            # Not a failure: the next refresh prunes these, and a database
            # change that drops accounts should not be blocked over it.
            notes.append(f"{len(stray)} entries are for accounts no longer in "
                         "accounts.json; the next refresh will drop them")

    return problems, notes


def main() -> int:
    if not PROFILES_PATH.exists():
        print(f"{PROFILES_PATH} does not exist", file=sys.stderr)
        return 1
    try:
        problems, notes = check(PROFILES_PATH, ACCOUNTS_PATH)
    except (ValueError, KeyError) as exc:
        print(f"{PROFILES_PATH}: {exc}", file=sys.stderr)
        return 1

    for note in notes:
        print(f"::notice::profiles.json {note}")
    for problem in problems:
        print(f"::error::profiles.json {problem}")
    if problems:
        return 1

    raw = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    oldest = min(raw["fetched"]) if raw["fetched"] else 0
    newest = max(raw["fetched"]) if raw["fetched"] else 0
    print(f"profiles.json: {raw['count']} entries, generated {raw['generated_at']}, "
          f"fetch days {profiles.day_to_iso(oldest)}..{profiles.day_to_iso(newest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
