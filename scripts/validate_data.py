#!/usr/bin/env python3
import csv, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'data'/'normalized'
def rows(name):
    with (D/name).open(encoding='utf-8',newline='') as f: return list(csv.DictReader(f))
accounts=rows('accounts.csv'); sources=rows('sources.csv'); flags=rows('flags.csv'); records=rows('source_records.csv'); profiles=rows('source_profiles.csv'); confidence=rows('confidence.csv')
sids={r['steamid64'] for r in accounts}; srcs={r['source_id'] for r in sources}; profsrc={r['source_id'] for r in profiles}
assert len(sids)==len(accounts), 'duplicate accounts'
assert len(srcs)==len(sources), 'duplicate sources'
assert srcs==profsrc, 'every registered source must have a confidence profile'
assert all(r['steamid64'] in sids and r['source_id'] in srcs for r in flags), 'orphan flag'
assert all(r['steamid64'] in sids and r['source_id'] in srcs for r in records), 'orphan source record'
assert {r['steamid64'] for r in confidence}==sids, 'confidence export does not cover every account'
for r in records: json.loads(r['raw_record'])
for r in profiles: assert 0 <= float(r['base_weight']) <= 100
print(f"OK: {len(accounts)} accounts, {len(records)} source records, {len(flags)} flags, {len(sources)} registered sources")
