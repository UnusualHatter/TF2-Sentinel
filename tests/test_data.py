from pathlib import Path
import csv
BASE=76561197960265728
ROOT=Path(__file__).resolve().parents[1]

def test_account_ids_match_steam64():
    with (ROOT/"data/normalized/accounts.csv").open(encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            assert int(r["steamid64"]) == BASE + int(r["account_id"])
