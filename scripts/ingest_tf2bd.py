#!/usr/bin/env python3
import argparse
import csv
import json
import sys
import hashlib
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.steamid import to_steam3

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "normalized"

def load_csv(name: str):
    path = DATA_DIR / name
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def save_csv(name: str, fieldnames: list[str], rows: list[dict]):
    path = DATA_DIR / name
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "TF2Sentinel/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--url", required=True)
    args = ap.parse_args()

    source_id = str(int(args.source_id))

    try:
        data = fetch(args.url)
    except Exception as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1

    players = data.get("players", [])
    print(f"Fetched {len(players)} players from {args.url}")

    acc_fields, acc_rows = load_csv("accounts.csv")
    rec_fields, rec_rows = load_csv("source_records.csv")
    flag_fields, flag_rows = load_csv("flags.csv")
    alias_fields, alias_rows = load_csv("aliases.csv")
    ev_fields, ev_rows = load_csv("evidence.csv")

    existing_accounts = {r["steamid64"] for r in acc_rows}
    
    existing_hashes = {r["record_hash"] for r in rec_rows}
    next_record_id = max((int(r["source_record_id"]) for r in rec_rows), default=0) + 1
    next_record_index = max((int(r["record_index"]) for r in rec_rows if r["source_id"] == source_id), default=-1) + 1

    flags_by_key = {(f["steamid64"], f["source_id"], f["flag"]): f for f in flag_rows}
    next_flag_id = max((int(f["flag_id"]) for f in flag_rows), default=0) + 1

    existing_alias_keys = {(a["steamid64"], a["source_id"], a["player_name"]) for a in alias_rows}
    next_alias_id = max((int(a["alias_id"]) for a in alias_rows), default=0) + 1

    existing_evidence_keys = {(e["steamid64"], e["source_id"], e["content"]) for e in ev_rows}
    next_evidence_id = max((int(e["evidence_id"]) for e in ev_rows), default=0) + 1

    new_accs, new_recs, new_flags, new_aliases, new_evs = 0, 0, 0, 0, 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for p in players:
        sid_raw = p.get("steamid")
        if not sid_raw:
            continue
            
        import re
        steamid64 = ""
        if sid_raw.startswith("[U:1:"):
            m = re.match(r"\[U:1:(\d+)\]", sid_raw)
            if m:
                steamid64 = str(int(m.group(1)) + 76561197960265728)
        elif sid_raw.startswith("STEAM_"):
            m = re.match(r"STEAM_[0-5]:([0-1]):(\d+)", sid_raw)
            if m:
                y, z = int(m.group(1)), int(m.group(2))
                steamid64 = str(z * 2 + y + 76561197960265728)
        elif sid_raw.isdigit() and len(sid_raw) == 17:
            steamid64 = sid_raw
        
        if not steamid64:
            continue
            
        if steamid64 not in existing_accounts:
            acc_rows.append({
                "steamid64": steamid64,
                "steam3": to_steam3(int(steamid64)),
                "first_observed_at": now,
                "last_observed_at": now,
            })
            existing_accounts.add(steamid64)
            new_accs += 1
            
        raw_record_json = json.dumps(p, ensure_ascii=False, sort_keys=True)
        rhash = hashlib.sha256(raw_record_json.encode("utf-8")).hexdigest()
        
        if rhash in existing_hashes:
            continue
            
        rec_rows.append({
            "source_record_id": str(next_record_id),
            "source_id": source_id,
            "steamid64": steamid64,
            "raw_steam_id": sid_raw,
            "record_index": str(next_record_index),
            "normalization_note": "",
            "record_hash": rhash,
            "raw_record": raw_record_json,
        })
        existing_hashes.add(rhash)
        next_record_id += 1
        next_record_index += 1
        new_recs += 1

        attrs = p.get("attributes", [])
        if attrs:
            for attr in attrs:
                mapped_flag = "suspicious"
                if attr in ("cheater", "bot", "suspicious", "exploiter"):
                    mapped_flag = attr
                fkey = (steamid64, source_id, mapped_flag)
                if fkey not in flags_by_key:
                    flags_by_key[fkey] = {
                        "flag_id": str(next_flag_id),
                        "source_id": source_id,
                        "steamid64": steamid64,
                        "flag": mapped_flag,
                        "active": "true"
                    }
                    flag_rows.append(flags_by_key[fkey])
                    next_flag_id += 1
                    new_flags += 1

        proof = p.get("proof") or p.get("reason")
        if proof:
            proof_str = "; ".join(proof) if isinstance(proof, list) else str(proof)
            ekey = (steamid64, source_id, proof_str)
            if ekey not in existing_evidence_keys:
                ev_rows.append({
                    "evidence_id": str(next_evidence_id),
                    "source_id": source_id,
                    "steamid64": steamid64,
                    "evidence_type": "reason",
                    "content": proof_str
                })
                existing_evidence_keys.add(ekey)
                next_evidence_id += 1
                new_evs += 1
                
        last_seen = p.get("last_seen", {})
        if "player_name" in last_seen and last_seen["player_name"]:
            name = last_seen["player_name"]
            akey = (steamid64, source_id, name)
            if akey not in existing_alias_keys:
                alias_rows.append({
                    "alias_id": str(next_alias_id),
                    "source_id": source_id,
                    "steamid64": steamid64,
                    "player_name": name,
                    "observed_at": now
                })
                existing_alias_keys.add(akey)
                next_alias_id += 1
                new_aliases += 1

    save_csv("accounts.csv", acc_fields, acc_rows)
    save_csv("source_records.csv", rec_fields, rec_rows)
    save_csv("flags.csv", flag_fields, flag_rows)
    save_csv("aliases.csv", alias_fields, alias_rows)
    save_csv("evidence.csv", ev_fields, ev_rows)

    print(f"Added {new_accs} accounts, {new_recs} records, {new_flags} flags, {new_aliases} aliases, {new_evs} evidence")
    return 0

if __name__ == "__main__":
    sys.exit(main())
