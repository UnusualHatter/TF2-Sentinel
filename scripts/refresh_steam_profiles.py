#!/usr/bin/env python3
"""Refresh docs/data/profiles.json from the Steam Web API.

Every account in docs/data/accounts.json gets one entry holding the persona
name and avatar Steam currently serves for it. The website reads that file
instead of asking Steam anything itself, so a visitor causes one request for
the whole database rather than one request per account.

The API key is read from STEAM_WEB_API_KEY and never appears in the output or
in any message this script prints.

Run with no arguments to refresh everything that has not been checked today:

    STEAM_WEB_API_KEY=... python3 scripts/refresh_steam_profiles.py

A run that cannot reach Steam leaves the published file untouched. A run that
reaches Steam for some batches and not others keeps the previous values for
the batches that failed; nothing is ever replaced by a blank.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import profiles  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_PATH = ROOT / "docs" / "data" / "accounts.json"
PROFILES_PATH = ROOT / "docs" / "data" / "profiles.json"

API_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
# GetPlayerSummaries documents a hard limit of 100 IDs per call.
MAX_BATCH = 100
USER_AGENT = "TF2-Sentinel-profile-refresh/1 (+https://github.com/UnusualHatter/TF2-Sentinel)"

# Steam publishes no rate limit for this endpoint, so the defaults stay well
# below anything that could plausibly be one: two calls at a time with a short
# pause between them covers 36,000 accounts in a couple of minutes.
DEFAULT_CONCURRENCY = 2
DEFAULT_DELAY = 0.2
DEFAULT_ATTEMPTS = 4
DEFAULT_TIMEOUT = 20.0
BACKOFF_BASE = 2.0
BACKOFF_CAP = 60.0

# Refuse to drop entries if accounts.json suddenly describes a much smaller
# database than the cache does; that means the input is broken, not that
# 30,000 accounts were deleted.
PRUNE_SAFETY_RATIO = 0.5


class SteamUnavailable(Exception):
    """A batch could not be retrieved after every attempt."""


def redactor(secret: str):
    def redact(text: object) -> str:
        text = str(text)
        return text.replace(secret, "***") if secret else text
    return redact


def load_account_ids(path: Path) -> tuple[list[int], dict[int, dict]]:
    """Return the account keys in accounts.json plus any legacy profile data."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} does not contain a list")

    ids: list[int] = []
    legacy: dict[int, dict] = {}
    seen: set[int] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        suffix = profiles.suffix_of(row.get("steamid64"))
        if suffix is None or suffix in seen:
            continue
        seen.add(suffix)
        ids.append(suffix)
        hash_value = profiles.avatar_hash(row.get("avatar_url") or "")
        name = row.get("steam_persona_name") or ""
        if hash_value or name:
            legacy[suffix] = profiles.new_entry(
                name=name if isinstance(name, str) else "",
                hash_value=hash_value or profiles.NO_AVATAR,
            )
    return ids, legacy


def select_targets(store: dict[int, dict], account_ids: list[int], today: int,
                   force: bool, limit: int) -> list[int]:
    """Stalest accounts first, so a capped run still makes progress every time."""
    candidates = []
    for suffix in account_ids:
        fetched = store.get(suffix, {}).get("fetched", 0)
        if not force and fetched >= today:
            continue
        candidates.append((fetched, suffix))
    candidates.sort()
    return [suffix for _, suffix in candidates[:limit]]


def batched(items: list[int], size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def parse_players(body: bytes) -> list[dict]:
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("response is not an object")
    response = payload.get("response")
    if not isinstance(response, dict):
        raise ValueError("response envelope missing")
    players = response.get("players")
    if players is None:
        return []
    if not isinstance(players, list):
        raise ValueError("players is not a list")
    return [p for p in players if isinstance(p, dict)]


def entry_from_player(player: dict, today: int, previous: dict | None) -> tuple[int, dict] | None:
    """Turn one API player object into a cache entry, or None if unusable."""
    suffix = profiles.suffix_of(player.get("steamid"))
    if suffix is None:
        return None

    hash_value = profiles.avatar_hash(player.get("avatarmedium") or "")
    if not hash_value:
        hash_value = profiles.avatar_hash(player.get("avatarfull") or "")
    if not hash_value:
        raw = player.get("avatarhash")
        if isinstance(raw, str) and len(raw) == profiles.HASH_LENGTH and all(
                c in "0123456789abcdef" for c in raw):
            hash_value = raw
    if not hash_value:
        # Steam answered but the avatar field was missing or in a shape this
        # script does not recognize: keep whatever was published before.
        hash_value = (previous or {}).get("hash", profiles.NO_AVATAR)

    name = player.get("personaname")
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        name = (previous or {}).get("name", "")

    visibility = player.get("communityvisibilitystate")
    state = profiles.STATE_PUBLIC if visibility == 3 else profiles.STATE_LIMITED

    return suffix, profiles.new_entry(name=name, hash_value=hash_value,
                                      fetched=today, state=state)


class Fetcher:
    def __init__(self, key: str, timeout: float, attempts: int, delay: float,
                 opener: urllib.request.OpenerDirector | None = None,
                 sleep=time.sleep):
        self.key = key
        self.timeout = timeout
        self.attempts = attempts
        self.delay = delay
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep
        self.redact = redactor(key)
        self.requests = 0
        self._lock = threading.Lock()

    def _count(self) -> None:
        with self._lock:
            self.requests += 1

    def _once(self, steamids: list[int]) -> list[dict]:
        query = urllib.parse.urlencode({
            "key": self.key,
            "steamids": ",".join(profiles.steamid64_of(s) for s in steamids),
        })
        request = urllib.request.Request(f"{API_URL}?{query}",
                                         headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/json"})
        self._count()
        with self.opener.open(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise urllib.error.HTTPError(API_URL, response.status, "unexpected status",
                                             response.headers, None)
            return parse_players(response.read())

    def batch(self, steamids: list[int]) -> list[dict]:
        last = ""
        for attempt in range(1, self.attempts + 1):
            try:
                players = self._once(steamids)
                if self.delay:
                    self.sleep(self.delay)
                return players
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
                # 401/403 mean the key is wrong or revoked; retrying cannot fix
                # that and would only burn the workflow's time.
                if exc.code in (400, 401, 403):
                    raise SteamUnavailable(self.redact(last)) from None
                retry_after = _retry_after(exc)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = self.redact(f"{type(exc).__name__}: {exc}")
                retry_after = None
            except ValueError as exc:
                last = self.redact(f"malformed response: {exc}")
                retry_after = None

            if attempt == self.attempts:
                break
            wait = retry_after if retry_after is not None else min(
                BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            self.sleep(wait + random.uniform(0, 0.5))
        raise SteamUnavailable(self.redact(last))


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    try:
        value = exc.headers.get("Retry-After") if exc.headers else None
    except AttributeError:
        return None
    if not value:
        return None
    try:
        return min(BACKOFF_CAP, max(0.0, float(value)))
    except ValueError:
        return None


def refresh(store: dict[int, dict], targets: list[int], fetcher: Fetcher,
            batch_size: int, concurrency: int, today: int, log=print) -> tuple[int, int, int]:
    """Fetch every batch and merge the results. Returns (updated, changed, failed)."""
    batches = list(batched(targets, batch_size))
    if not batches:
        return 0, 0, 0

    results: list[tuple[int, list[dict] | None]] = []
    lock = threading.Lock()

    def run(index: int, chunk: list[int]) -> None:
        try:
            players = fetcher.batch(chunk)
        except SteamUnavailable as exc:
            log(f"  batch {index + 1}/{len(batches)} failed: {exc}")
            players = None
        with lock:
            results.append((index, players))

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for index, chunk in enumerate(batches):
            pool.submit(run, index, chunk)

    updated = changed = failed = 0
    seen_ids: set[int] = set()
    # Sorted so a run produces the same file no matter what order the batches
    # happened to come back in.
    for index, players in sorted(results, key=lambda item: item[0]):
        if players is None:
            failed += 1
            continue
        for player in players:
            parsed = entry_from_player(player, today, store.get(profiles.suffix_of(player.get("steamid")) or -1))
            if parsed is None:
                continue
            suffix, entry = parsed
            seen_ids.add(suffix)
            previous = store.get(suffix)
            if previous is None or previous["hash"] != entry["hash"] or previous["name"] != entry["name"]:
                changed += 1
            store[suffix] = entry
            updated += 1
        for suffix in batches[index]:
            if suffix in seen_ids:
                continue
            # Steam answered without this account: it is deleted or the ID was
            # never real. Keep the last known values and record why.
            entry = store.get(suffix) or profiles.new_entry()
            entry = dict(entry)
            entry["fetched"] = today
            entry["state"] = profiles.STATE_MISSING
            store[suffix] = entry
    return updated, changed, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accounts", type=Path, default=ACCOUNTS_PATH)
    parser.add_argument("--profiles", type=Path, default=PROFILES_PATH)
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH,
                        help=f"SteamIDs per API call (max {MAX_BATCH})")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help="seconds to pause after each successful call")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-requests", type=int, default=1000,
                        help="upper bound on API calls for one run")
    parser.add_argument("--force", action="store_true",
                        help="refresh accounts already checked today")
    parser.add_argument("--no-seed", action="store_true",
                        help="do not carry avatar_url from accounts.json for unknown accounts")
    parser.add_argument("--no-prune", action="store_true",
                        help="keep entries for accounts no longer in the database")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing or calling Steam")
    args = parser.parse_args(argv)

    batch_size = max(1, min(MAX_BATCH, args.batch_size))
    if args.batch_size > MAX_BATCH:
        print(f"batch size capped at {MAX_BATCH}", file=sys.stderr)

    try:
        account_ids, legacy = load_account_ids(args.accounts)
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.accounts}: {exc}", file=sys.stderr)
        return 1
    if not account_ids:
        print(f"{args.accounts} has no usable SteamID64 values", file=sys.stderr)
        return 1

    try:
        store = profiles.load(args.profiles)
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.profiles}: {exc}", file=sys.stderr)
        return 1

    if not args.no_prune:
        if len(account_ids) < len(store) * PRUNE_SAFETY_RATIO:
            print(f"refusing to prune: accounts.json has {len(account_ids)} accounts "
                  f"but the cache has {len(store)}", file=sys.stderr)
        else:
            wanted = set(account_ids)
            for suffix in [s for s in store if s not in wanted]:
                del store[suffix]

    seeded = 0
    if not args.no_seed:
        for suffix in account_ids:
            if suffix in store or suffix not in legacy:
                continue
            store[suffix] = dict(legacy[suffix])
            seeded += 1

    today = profiles.today_index()
    limit = max(0, args.max_requests) * batch_size
    targets = select_targets(store, account_ids, today, args.force, limit)

    print(f"accounts: {len(account_ids)} · cached: {len(store)} · seeded: {seeded} · "
          f"to refresh: {len(targets)} in {-(-len(targets) // batch_size)} calls")

    updated = changed = failed = 0
    if args.dry_run:
        print("dry run: Steam was not contacted and nothing was written")
    elif targets:
        key = (os.environ.get("STEAM_WEB_API_KEY") or "").strip()
        if not key:
            print("STEAM_WEB_API_KEY is not set", file=sys.stderr)
            return 1
        fetcher = Fetcher(key, args.timeout, max(1, args.attempts), max(0.0, args.delay))
        updated, changed, failed = refresh(store, targets, fetcher, batch_size,
                                           args.concurrency, today)
        total_batches = -(-len(targets) // batch_size)
        print(f"api calls: {fetcher.requests} · players updated: {updated} · "
              f"profiles changed: {changed} · failed batches: {failed}/{total_batches}")
        if failed == total_batches:
            print("every batch failed; leaving the published cache untouched", file=sys.stderr)
            return 1

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document = profiles.encode(store, generated_at)

    if args.dry_run:
        return 0
    if not profiles.payload_changed(args.profiles, document):
        print("no profile data changed; leaving the file as it is")
        return 0

    profiles.write(args.profiles, document)
    print(f"wrote {args.profiles} ({document['count']} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
