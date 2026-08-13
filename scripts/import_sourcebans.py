#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path

import psycopg

BASE = 76561197960265728
STEAM3 = re.compile(r"^\[U:(\d+):(\d+)\]$")
STEAM2 = re.compile(r"^STEAM_[0-5]:([01]):(\d+)$")


def normalize(raw: str):
    raw = str(raw).strip()
    if raw.isdigit() and int(raw) >= BASE:
        sid64 = int(raw)
        return sid64, sid64 - BASE, f"[U:1:{sid64 - BASE}]"
    m = STEAM3.match(raw)
    if m:
        account_id = int(m.group(2))
        return BASE + account_id, account_id, f"[U:1:{account_id}]"
    m = STEAM2.match(raw)
    if m:
        account_id = int(m.group(2)) * 2 + int(m.group(1))
        return BASE + account_id, account_id, f"[U:1:{account_id}]"
    raise ValueError(f"unsupported Steam ID: {raw}")


def main():
    ap = argparse.ArgumentParser(description="Import a scrape_sourcebans.py snapshot into PostgreSQL.")
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--dsn", default="postgresql://cheaterdb:change-me@localhost:5432/cheaterdb")
    ap.add_argument("--server-name", required=True)
    ap.add_argument("--region", default="South America")
    ap.add_argument("--country-code", default=None)
    args = ap.parse_args()

    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    source_url = data.get("source", "")
    rows = data.get("records", [])
    source_slug = "sourcebans-" + re.sub(r"[^a-z0-9]+", "-", args.server_name.lower()).strip("-")

    imported = 0
    skipped = 0
    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_id FROM sources WHERE slug=%s", (source_slug,))
            row = cur.fetchone()
            if row:
                source_id = row[0]
            else:
                cur.execute("SELECT COALESCE(MAX(source_id), 0) + 1 FROM sources")
                source_id = cur.fetchone()[0]
                cur.execute(
                    """INSERT INTO sources
                       (source_id, slug, name, source_type, upstream_repo, update_url, authors, scope_region, description, source_file)
                       VALUES (%s,%s,%s,'sourcebans','',%s,'[]'::jsonb,%s,%s,%s)""",
                    (source_id, source_slug, args.server_name + " SourceBans", source_url, args.region,
                     "Public SourceBans snapshot", str(args.snapshot)),
                )

            cur.execute(
                """INSERT INTO servers (name, region, country_code, sourcebans_url)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (name, sourcebans_url) DO UPDATE SET
                     region=EXCLUDED.region, country_code=EXCLUDED.country_code
                   RETURNING server_id""",
                (args.server_name, args.region, args.country_code, source_url),
            )
            server_id = cur.fetchone()[0]

            for rec in rows:
                try:
                    sid64, account_id, steam3 = normalize(rec["steam_id"])
                except (KeyError, ValueError):
                    skipped += 1
                    continue

                cur.execute(
                    """INSERT INTO accounts (steamid64, account_id, steam3)
                       VALUES (%s,%s,%s)
                       ON CONFLICT (steamid64) DO NOTHING""",
                    (sid64, account_id, steam3),
                )
                raw = json.dumps(rec, ensure_ascii=False, sort_keys=True)
                ext_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
                row_text = rec.get("row_text", "")
                links = rec.get("links") or []
                detail_url = links[0] if links else rec.get("source_url") or source_url
                cur.execute(
                    """INSERT INTO bans
                       (steamid64, server_id, source_id, external_ban_id, reason, source_url, raw_record)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT (server_id, external_ban_id) DO NOTHING""",
                    (sid64, server_id, source_id, ext_id, row_text, detail_url, raw),
                )
                imported += cur.rowcount
        conn.commit()
    print(f"imported {imported} bans; skipped {skipped} unrecognized rows")


if __name__ == "__main__":
    main()
