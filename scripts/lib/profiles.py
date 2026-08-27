"""Read and write docs/data/profiles.json, the published Steam profile cache.

The file is columnar rather than one object per account: the site fetches it on
every page load, and 36,000 small objects cost far more to parse and to keep in
memory than a handful of parallel arrays. It also keeps the diff small, because
a refresh that only changes timestamps rewrites one contiguous region of the
file instead of scattering edits through it.

Entries are keyed by the last ten digits of the SteamID64. Every SteamID64 in
this database starts with the same seven digits, so storing the whole thing
would waste about a third of the file.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

FORMAT_VERSION = 1

ID_PREFIX = "7656119"
STEAMID64_RE = re.compile(r"^7656119\d{10}$")

# Steam hands the same avatar out under several CDN hostnames and the one it
# picks changes over time. Only the hash identifies the image, so that is all
# that gets stored; the site rebuilds the URL from these two constants.
AVATAR_BASE = "https://avatars.steamstatic.com/"
AVATAR_SIZE = "_medium.jpg"
AVATAR_HASH_RE = re.compile(r"^https://[a-z0-9.-]*steamstatic\.com/([0-9a-f]{40})_(?:medium|full)\.jpg$")
HASH_LENGTH = 40
NO_AVATAR = "0" * HASH_LENGTH

# state values published alongside each entry
STATE_UNKNOWN = 0    # carried over from older data, never confirmed against Steam
STATE_PUBLIC = 1     # Steam returned the profile and it is public
STATE_LIMITED = 2    # Steam returned the profile but it is private/friends-only
STATE_MISSING = 3    # Steam has no player for this ID (deleted, or never existed)

EPOCH = date(1970, 1, 1)


def today_index() -> int:
    return (datetime.now(timezone.utc).date() - EPOCH).days


def day_to_iso(day_index: int) -> str:
    return date.fromordinal(EPOCH.toordinal() + day_index).isoformat()


def suffix_of(steamid64: str) -> int | None:
    """Ten-digit key for a SteamID64, or None if it is not one we can store."""
    if not isinstance(steamid64, str) or not STEAMID64_RE.match(steamid64):
        return None
    return int(steamid64[len(ID_PREFIX):])


def steamid64_of(suffix: int) -> str:
    return f"{ID_PREFIX}{suffix:010d}"


def avatar_hash(url: str) -> str | None:
    """Extract the image hash from a Steam avatar URL, or None if unrecognized."""
    if not isinstance(url, str):
        return None
    match = AVATAR_HASH_RE.match(url.strip())
    return match.group(1) if match else None


def avatar_url(hash_value: str) -> str:
    if not hash_value or hash_value == NO_AVATAR:
        return ""
    return f"{AVATAR_BASE}{hash_value}{AVATAR_SIZE}"


def new_entry(name: str = "", hash_value: str = NO_AVATAR, fetched: int = 0,
              state: int = STATE_UNKNOWN) -> dict:
    return {"name": name, "hash": hash_value, "fetched": fetched, "state": state}


def load(path: Path) -> dict[int, dict]:
    """Load the published cache. A missing file is an empty cache, not an error."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return decode(raw)


def decode(raw: dict) -> dict[int, dict]:
    version = raw.get("version")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported profiles.json version: {version!r}")

    ids = raw.get("ids") or []
    names = raw.get("names") or []
    blob = raw.get("avatars") or ""
    fetched = raw.get("fetched") or []
    states = raw.get("state") or []
    if not (len(ids) == len(names) == len(fetched) == len(states)):
        raise ValueError("profiles.json columns have different lengths")
    if len(blob) != len(ids) * HASH_LENGTH:
        raise ValueError("profiles.json avatar blob does not match the number of entries")

    store = {}
    for i, suffix in enumerate(ids):
        store[int(suffix)] = new_entry(
            name=names[i],
            hash_value=blob[i * HASH_LENGTH:(i + 1) * HASH_LENGTH],
            fetched=int(fetched[i]),
            state=int(states[i]),
        )
    return store


def encode(store: dict[int, dict], generated_at: str) -> dict:
    ids = sorted(store)
    return {
        "version": FORMAT_VERSION,
        "generated_at": generated_at,
        "count": len(ids),
        "id_prefix": ID_PREFIX,
        "avatar_base": AVATAR_BASE,
        "avatar_size": AVATAR_SIZE,
        "hash_length": HASH_LENGTH,
        "ids": ids,
        "names": [store[i]["name"] for i in ids],
        "avatars": "".join(store[i]["hash"] for i in ids),
        "fetched": [store[i]["fetched"] for i in ids],
        "state": [store[i]["state"] for i in ids],
    }


def payload_changed(path: Path, document: dict) -> bool:
    """True if anything but generated_at differs from what is already published."""
    if not path.exists():
        return True
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    a = {k: v for k, v in existing.items() if k != "generated_at"}
    b = {k: v for k, v in document.items() if k != "generated_at"}
    return a != b


def write(path: Path, document: dict) -> None:
    """Write the file in one step, so a crash cannot leave a truncated cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".profiles-", suffix=".json")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        # mkstemp creates the file 0600; the published data is world-readable.
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
