#!/usr/bin/env python3
"""Look up SourceBans records for known accounts through the SteamHistory API.

SteamHistory aggregates the ban lists of many communities. Asking it about the
accounts already in this database turns up bans from servers that have never
been imported here directly, without scraping each of those servers.

This only downloads and normalizes. It writes one JSON file and never touches
data/normalized/, because how the result should be scored is a decision that
belongs with the source catalog, not with a fetcher. Every record keeps the
community that issued the ban in `server`; SteamHistory is recorded as the
route it arrived by, not as the source of the ban.

    STEAMHISTORY_API_KEY=... python3 scripts/fetch_steamhistory_bans.py \
        --out /tmp/steamhistory.json --max-requests 20

The API answers HTTP 200 even when it rejects the request, putting the problem
in an `error` field instead, so the status code alone means nothing here.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
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

from lib.classify import classify_reason  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_PATH = ROOT / "docs" / "data" / "accounts.json"
SOURCES_PATH = ROOT / "docs" / "data" / "sources.json"

API_URL = "https://steamhistory.net/api/sourcebans"
# Documented maximum for the steamids parameter.
MAX_BATCH = 100
USER_AGENT = "TF2-Sentinel-steamhistory-import/1 (+https://github.com/UnusualHatter/TF2-Sentinel)"

DEFAULT_CONCURRENCY = 2
DEFAULT_DELAY = 0.25
DEFAULT_ATTEMPTS = 4
DEFAULT_TIMEOUT = 30.0
BACKOFF_BASE = 2.0
BACKOFF_CAP = 60.0

STEAMID64_RE = re.compile(r"^7656119\d{10}$")
# CurrentState values the API documents. Anything else is kept verbatim but
# reported, so a new state cannot be silently misread as an active ban.
KNOWN_STATES = ("Permanent", "Temp-Ban", "Expired", "Unbanned")
ACTIVE_STATES = ("Permanent", "Temp-Ban")


class SteamHistoryUnavailable(Exception):
    """A batch could not be retrieved after every attempt."""


class SteamHistoryRejected(Exception):
    """The API answered, but refused the request. Retrying will not help."""


def redactor(secret: str):
    def redact(text: object) -> str:
        text = str(text)
        return text.replace(secret, "***") if secret else text
    return redact


def load_account_ids(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} does not contain a list")
    seen: dict[str, None] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        steamid64 = row.get("steamid64")
        if isinstance(steamid64, str) and STEAMID64_RE.match(steamid64):
            seen.setdefault(steamid64, None)
    return list(seen)


def load_ids_file(path: Path) -> list[str]:
    seen: dict[str, None] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if STEAMID64_RE.match(value):
            seen.setdefault(value, None)
    return list(seen)


def batched(items: list[str], size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def source_matcher(sources: list[dict]):
    """Suggest which registered source a SteamHistory server name refers to.

    Only a suggestion: a match means the two are probably the same community,
    and that the records are therefore a mirror of a source already imported
    rather than independent evidence. Someone has to confirm that before the
    records are given a confidence weight, which is why nothing here decides it.
    """
    entries = []
    for source in sources:
        slug = str(source.get("slug") or "")
        if not slug:
            continue
        names = {normalize_name(slug), normalize_name(source.get("short_name")),
                 normalize_name(source.get("name"))}
        # Community names are written differently in each place: "Panda-Community"
        # against the panda-sourcebans slug, "DISC-FF" against discff-community-bans.
        names.add(re.sub(r"(sourcebans|communitybans|bans|community)$", "", normalize_name(slug)))
        entries.append((slug, {n for n in names if len(n) >= 3}))

    def match(server: str) -> tuple[list[str], str]:
        needle = normalize_name(server)
        if len(needle) < 3:
            return [], "none"
        exact = [slug for slug, names in entries if needle in names]
        if exact:
            return exact, "exact"
        prefix = [slug for slug, names in entries
                  if any(name.startswith(needle) or needle.startswith(name) for name in names)]
        if prefix:
            # Several communities share a prefix (three UGC sources, for one),
            # so every candidate is reported rather than one being picked.
            return prefix, "prefix"
        return [], "none"

    return match


def normalize_record(raw: dict, requested: set[str]) -> dict | None:
    """Turn one API record into a Sentinel row, or None if it is unusable."""
    if not isinstance(raw, dict):
        return None
    steamid64 = raw.get("SteamID")
    if not isinstance(steamid64, str) or not STEAMID64_RE.match(steamid64):
        return None
    if requested and steamid64 not in requested:
        # The API answered about an account this run did not ask for.
        return None

    server = raw.get("Server")
    if not isinstance(server, str) or not server.strip():
        return None

    def text(field: str) -> str:
        value = raw.get(field)
        return value.strip() if isinstance(value, str) else ""

    def epoch(field: str) -> int:
        value = raw.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0
        value = int(value)
        return value if 0 < value < 4102444800 else 0

    reason = text("BanReason")
    state = text("CurrentState")
    return {
        "steamid64": steamid64,
        "name": text("Name"),
        "server": server.strip(),
        "state": state,
        "active": state in ACTIVE_STATES,
        "reason": reason,
        "unban_reason": text("UnbanReason"),
        "banned_at": epoch("BanTimestamp"),
        "unbanned_at": epoch("UnbanTimestamp"),
        # Same classifier the rest of the pipeline uses, so a reason means the
        # same thing here as it does in a directly imported ban list.
        "flag": classify_reason(reason),
        "via": "steamhistory",
    }


def record_key(record: dict) -> tuple:
    return (record["steamid64"], record["server"], record["banned_at"], record["reason"])


class Fetcher:
    def __init__(self, key: str, timeout: float, attempts: int, delay: float,
                 opener: urllib.request.OpenerDirector | None = None, sleep=time.sleep):
        self.key = key
        self.timeout = timeout
        self.attempts = attempts
        self.delay = delay
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep
        self.redact = redactor(key)
        self.requests = 0
        self._lock = threading.Lock()

    def _once(self, steamids: list[str]) -> list[dict]:
        query = urllib.parse.urlencode({"key": self.key, "steamids": ",".join(steamids)})
        request = urllib.request.Request(f"{API_URL}?{query}",
                                         headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/json"})
        with self._lock:
            self.requests += 1
        with self.opener.open(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("response is not an object")
        # A rejected request still comes back as HTTP 200.
        if payload.get("error"):
            raise SteamHistoryRejected(self.redact(payload["error"]))
        records = payload.get("response")
        if records is None:
            return []
        if isinstance(records, dict):
            # shouldkey=1 shape, in case the default ever changes.
            flat = []
            for value in records.values():
                flat.extend(value if isinstance(value, list) else [value])
            return [r for r in flat if isinstance(r, dict)]
        if not isinstance(records, list):
            raise ValueError("response is not a list")
        return [r for r in records if isinstance(r, dict)]

    def batch(self, steamids: list[str]) -> list[dict]:
        last = ""
        for attempt in range(1, self.attempts + 1):
            try:
                records = self._once(steamids)
                if self.delay:
                    self.sleep(self.delay)
                return records
            except SteamHistoryRejected:
                raise
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
                if exc.code in (400, 401, 403):
                    raise SteamHistoryRejected(self.redact(last)) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = self.redact(f"{type(exc).__name__}: {exc}")
            except ValueError as exc:
                last = self.redact(f"malformed response: {exc}")

            if attempt == self.attempts:
                break
            self.sleep(min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1))) + random.uniform(0, 0.5))
        raise SteamHistoryUnavailable(self.redact(last))


def collect(steamids: list[str], fetcher: Fetcher, batch_size: int, concurrency: int,
            log=print) -> tuple[list[dict], int, int]:
    """Fetch every batch. Returns (records, failed_batches, queried_accounts)."""
    batches = list(batched(steamids, batch_size))
    results: list[tuple[int, list[dict] | None]] = []
    lock = threading.Lock()
    rejected: list[str] = []

    def run(index: int, chunk: list[str]) -> None:
        try:
            records = fetcher.batch(chunk)
        except SteamHistoryRejected as exc:
            with lock:
                rejected.append(str(exc))
            records = None
        except SteamHistoryUnavailable as exc:
            log(f"  batch {index + 1}/{len(batches)} failed: {exc}")
            records = None
        with lock:
            results.append((index, records))

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for index, chunk in enumerate(batches):
            pool.submit(run, index, chunk)

    if rejected:
        raise SteamHistoryRejected(rejected[0])

    requested = set(steamids)
    seen: dict[tuple, dict] = {}
    failed = 0
    queried = 0
    # Sorted by batch so the output does not depend on completion order.
    for index, records in sorted(results, key=lambda item: item[0]):
        if records is None:
            failed += 1
            continue
        queried += len(batches[index])
        for raw in records:
            record = normalize_record(raw, requested)
            if record is None:
                continue
            seen.setdefault(record_key(record), record)

    ordered = sorted(seen.values(),
                     key=lambda r: (r["steamid64"], r["server"], r["banned_at"], r["reason"]))
    return ordered, failed, queried


def summarize_servers(records: list[dict], match) -> list[dict]:
    servers: dict[str, dict] = {}
    for record in records:
        entry = servers.setdefault(record["server"], {
            "server": record["server"], "records": 0, "accounts": set(),
            "active": 0, "cheating": 0,
        })
        entry["records"] += 1
        entry["accounts"].add(record["steamid64"])
        if record["active"]:
            entry["active"] += 1
        if record["flag"] in ("cheater", "bot"):
            entry["cheating"] += 1

    rows = []
    for entry in servers.values():
        slugs, confidence = match(entry["server"])
        rows.append({
            "server": entry["server"],
            "records": entry["records"],
            "accounts": len(entry["accounts"]),
            "active": entry["active"],
            "cheating_reasons": entry["cheating"],
            "registered_sources": slugs,
            "match": confidence,
        })
    rows.sort(key=lambda row: (-row["records"], row["server"]))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accounts", type=Path, default=ACCOUNTS_PATH)
    parser.add_argument("--sources", type=Path, default=SOURCES_PATH)
    parser.add_argument("--ids-file", type=Path,
                        help="one SteamID64 per line, instead of every account in the database")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-requests", type=int, default=0,
                        help="stop after this many API calls (0 = every account)")
    parser.add_argument("--offset", type=int, default=0,
                        help="skip this many accounts, to continue an interrupted run")
    args = parser.parse_args(argv)

    batch_size = max(1, min(MAX_BATCH, args.batch_size))
    if args.batch_size > MAX_BATCH:
        print(f"batch size capped at the documented maximum of {MAX_BATCH}", file=sys.stderr)

    try:
        steamids = (load_ids_file(args.ids_file) if args.ids_file
                    else load_account_ids(args.accounts))
    except (OSError, ValueError) as exc:
        print(f"cannot read the account list: {exc}", file=sys.stderr)
        return 1
    if not steamids:
        print("no usable SteamID64 values to look up", file=sys.stderr)
        return 1

    steamids = steamids[max(0, args.offset):]
    if args.max_requests > 0:
        steamids = steamids[:args.max_requests * batch_size]

    key = (os.environ.get("STEAMHISTORY_API_KEY") or "").strip()
    if not key:
        print("STEAMHISTORY_API_KEY is not set", file=sys.stderr)
        return 1

    calls = -(-len(steamids) // batch_size)
    print(f"looking up {len(steamids)} accounts in {calls} calls of {batch_size}")

    fetcher = Fetcher(key, args.timeout, max(1, args.attempts), max(0.0, args.delay))
    started = time.monotonic()
    try:
        records, failed, queried = collect(steamids, fetcher, batch_size, args.concurrency)
    except SteamHistoryRejected as exc:
        print(f"SteamHistory refused the request: {exc}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - started

    if failed == calls:
        print("every batch failed; nothing was written", file=sys.stderr)
        return 1

    try:
        sources = json.loads(args.sources.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sources = []
    servers = summarize_servers(records, source_matcher(sources))

    document = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z"),
        "endpoint": API_URL,
        "aggregator": "steamhistory",
        "accounts_queried": queried,
        "failed_batches": failed,
        "record_count": len(records),
        "servers": servers,
        "records": records,
    }
    if key in json.dumps(document):
        print("refusing to write: the API key appears in the output", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    unknown_states = sorted({r["state"] for r in records if r["state"] not in KNOWN_STATES})
    with_bans = len({r["steamid64"] for r in records})
    unmapped = [row for row in servers if not row["registered_sources"]]
    ambiguous = [row for row in servers if len(row["registered_sources"]) > 1]

    print(f"api calls: {fetcher.requests} · failed batches: {failed}/{calls} · {elapsed:.1f}s")
    print(f"records: {len(records)} across {len(servers)} servers, "
          f"covering {with_bans} of {queried} accounts")
    print(f"servers with no registered source: {len(unmapped)}")
    for row in unmapped[:15]:
        print(f"    {row['server']}: {row['records']} records, {row['accounts']} accounts")
    if ambiguous:
        print(f"servers matching more than one registered source: {len(ambiguous)}")
        for row in ambiguous:
            print(f"    {row['server']}: {', '.join(row['registered_sources'])}")
    if unknown_states:
        print(f"undocumented CurrentState values seen: {', '.join(unknown_states)}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
