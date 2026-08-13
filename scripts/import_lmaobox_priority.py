#!/usr/bin/env python3
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'normalized'
RAW = ROOT / 'data' / 'raw'
BASE = 76561197960265728

SECTIONS = {
    'bots.tf - Bot': {
        'slug': 'lmaobox-priority-bots-tf',
        'name': 'LMAOBox priority import — bots.tf Bot',
        'flag': 'bot',
        'weight': 85,
        'evidence_class': 'strong',
        'group': 'bots-tf',
        'method': 'compiled-bot-list',
        'counts': True,
    },
    'd3fc0n6 - Cheater': {
        'slug': 'lmaobox-priority-d3fc0n6-cheater',
        'name': 'LMAOBox priority import — d3fc0n6 Cheater',
        'flag': 'cheater',
        'weight': 85,
        'evidence_class': 'strong',
        'group': 'd3fc0n6-direct',
        'method': 'compiled-cheater-list',
        'counts': True,
    },
    'd3fc0n6 - Tacobot': {
        'slug': 'lmaobox-priority-d3fc0n6-tacobot',
        'name': 'LMAOBox priority import — d3fc0n6 Tacobot',
        'flag': 'cheater',
        'weight': 12,
        'evidence_class': 'very_weak',
        'group': 'tacobot',
        'method': 'compiled-community-report-list',
        'counts': True,
    },
    'd3fc0n6 - Pazer': {
        'slug': 'lmaobox-priority-d3fc0n6-pazer',
        'name': 'LMAOBox priority import — d3fc0n6 Pazer',
        'flag': 'cheater',
        'weight': 92,
        'evidence_class': 'strong',
        'group': 'pazer-official',
        'method': 'compiled-curated-list',
        'counts': True,
    },
    'MCDB - Cheaters': {
        'slug': 'lmaobox-priority-mcdb-cheaters',
        'name': 'LMAOBox priority import — MCDB Cheaters',
        'flag': 'cheater',
        'weight': 72,
        'evidence_class': 'moderate',
        'group': 'megacheaterdb',
        'method': 'compiled-curated-database',
        'counts': True,
    },
    'MCDB - Suspicious': {
        'slug': 'lmaobox-priority-mcdb-suspicious',
        'name': 'LMAOBox priority import — MCDB Suspicious',
        'flag': 'suspicious',
        'weight': 72,
        'evidence_class': 'moderate',
        'group': 'megacheaterdb',
        'method': 'compiled-suspicious-list',
        'counts': True,
    },
    'MCDB - Watched': {
        'slug': 'lmaobox-priority-mcdb-watched',
        'name': 'LMAOBox priority import — MCDB Watched',
        'flag': 'watched',
        'weight': 72,
        'evidence_class': 'moderate',
        'group': 'megacheaterdb',
        'method': 'compiled-watch-list',
        'counts': True,
    },
    'MCDB - Legit': {
        'slug': 'lmaobox-priority-mcdb-legit',
        'name': 'LMAOBox priority import — MCDB Legit',
        'flag': 'clear',
        'weight': 0,
        'evidence_class': 'none',
        'group': 'megacheaterdb',
        'method': 'compiled-legit-list',
        'counts': False,
    },
}


def read_csv(name):
    path = DATA / name
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f)), csv.DictReader(path.open(encoding='utf-8', newline='')).fieldnames


def write_csv(name, rows, fields):
    with (DATA / name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def steam2_to_ids(value):
    m = re.fullmatch(r'STEAM_[01]:([01]):(\d+)', value)
    if not m:
        raise ValueError(value)
    y = int(m.group(1))
    z = int(m.group(2))
    account_id = z * 2 + y
    steamid64 = BASE + account_id
    return str(steamid64), str(account_id), f'[U:1:{account_id}]'


def parse(path):
    section = None
    records = {key: [] for key in SECTIONS}
    for line_no, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('-- '):
            candidate = stripped[3:].strip()
            if candidate in SECTIONS:
                section = candidate
                continue
        match = re.search(r'playerlist\.SetPriority\("(STEAM_[01]:[01]:\d+)",\s*(-?\d+)\);', line)
        if match and section:
            steam2 = match.group(1)
            priority = int(match.group(2))
            steamid64, account_id, steam3 = steam2_to_ids(steam2)
            records[section].append({
                'steam2': steam2,
                'steamid64': steamid64,
                'account_id': account_id,
                'steam3': steam3,
                'priority': priority,
                'line': line_no,
            })
    return records


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: import_lmaobox_priority.py /path/to/playerlist.lua')
    src_path = Path(sys.argv[1]).resolve()
    if not src_path.exists():
        raise SystemExit(f'file not found: {src_path}')

    RAW.mkdir(parents=True, exist_ok=True)
    raw_rel = 'data/raw/lmaobox_priority_k13imz.lua'
    raw_path = ROOT / raw_rel
    if src_path != raw_path.resolve():
        shutil.copy2(src_path, raw_path)

    parsed = parse(raw_path)
    total = sum(len(v) for v in parsed.values())
    if total == 0:
        raise SystemExit('no playerlist.SetPriority records found')

    sources, source_fields = read_csv('sources.csv')
    profiles, profile_fields = read_csv('source_profiles.csv')
    accounts, account_fields = read_csv('accounts.csv')
    flags, flag_fields = read_csv('flags.csv')
    records, record_fields = read_csv('source_records.csv')

    source_by_slug = {r['slug']: r for r in sources}
    next_source_id = max(int(r['source_id']) for r in sources) + 1
    source_ids = {}

    for section, meta in SECTIONS.items():
        existing = source_by_slug.get(meta['slug'])
        if existing:
            source_id = int(existing['source_id'])
            existing.update({
                'name': meta['name'],
                'source_type': 'lmaobox_priority_import',
                'upstream_repo': '',
                'update_url': '',
                'authors': json.dumps(["Pianta's BotListConverter"], ensure_ascii=False),
                'scope_region': 'global',
                'description': f'Imported from the {section} section of the supplied LMAOBox player priority Lua file.',
                'source_file': raw_rel,
            })
        else:
            source_id = next_source_id
            next_source_id += 1
            row = {
                'source_id': str(source_id),
                'slug': meta['slug'],
                'name': meta['name'],
                'source_type': 'lmaobox_priority_import',
                'upstream_repo': '',
                'update_url': '',
                'authors': json.dumps(["Pianta's BotListConverter"], ensure_ascii=False),
                'scope_region': 'global',
                'description': f'Imported from the {section} section of the supplied LMAOBox player priority Lua file.',
                'source_file': raw_rel,
            }
            sources.append(row)
            source_by_slug[meta['slug']] = row
        source_ids[section] = source_id

    profile_by_id = {int(r['source_id']): r for r in profiles}
    for section, meta in SECTIONS.items():
        sid = source_ids[section]
        row = {
            'source_id': str(sid),
            'base_weight': str(meta['weight']),
            'evidence_class': meta['evidence_class'],
            'independence_group': meta['group'],
            'counts_toward_confidence': str(meta['counts']).lower(),
            'is_mirror': 'false',
            'assessment_method': meta['method'],
            'last_verified': '2026-08-12',
            'notes': 'The Lua file is a compiled transport format; source-family independence is preserved by independence_group.',
        }
        if sid in profile_by_id:
            profile_by_id[sid].update(row)
        else:
            profiles.append(row)
            profile_by_id[sid] = row

    target_ids = {str(x) for x in source_ids.values()}
    flags = [r for r in flags if r['source_id'] not in target_ids]
    records = [r for r in records if r['source_id'] not in target_ids]

    accounts_by_id = {r['steamid64']: r for r in accounts}
    new_flags = []
    new_records = []

    for section, items in parsed.items():
        meta = SECTIONS[section]
        sid = str(source_ids[section])
        for idx, item in enumerate(items):
            steamid64 = item['steamid64']
            if steamid64 not in accounts_by_id:
                row = {
                    'steamid64': steamid64,
                    'account_id': item['account_id'],
                    'steam3': item['steam3'],
                    'first_observed_at': '',
                    'last_observed_at': '',
                }
                accounts.append(row)
                accounts_by_id[steamid64] = row
            raw = {
                'section': section,
                'steam2': item['steam2'],
                'steamid64': steamid64,
                'priority': item['priority'],
                'line': item['line'],
                'container': raw_rel,
            }
            raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            digest = hashlib.sha256(f'{sid}\0{idx}\0{raw_json}'.encode()).hexdigest()
            new_records.append({
                'source_record_id': '0',
                'source_id': sid,
                'steamid64': steamid64,
                'raw_steam_id': item['steam2'],
                'record_index': str(idx),
                'normalization_note': f'priority={item["priority"]}',
                'record_hash': digest,
                'raw_record': raw_json,
            })
            new_flags.append({
                'flag_id': '0',
                'steamid64': steamid64,
                'source_id': sid,
                'flag': meta['flag'],
                'review_status': 'imported',
                'active': 'true',
                'observed_at': '',
            })

    records.extend(new_records)
    flags.extend(new_flags)

    accounts.sort(key=lambda r: int(r['steamid64']))
    sources.sort(key=lambda r: int(r['source_id']))
    profiles.sort(key=lambda r: int(r['source_id']))
    records.sort(key=lambda r: (int(r['source_id']), int(r['record_index']), int(r['steamid64'])))
    flags.sort(key=lambda r: (int(r['source_id']), int(r['steamid64']), r['flag']))

    dedup_flags = []
    seen = set()
    for row in flags:
        key = (row['steamid64'], row['source_id'], row['flag'])
        if key in seen:
            continue
        seen.add(key)
        dedup_flags.append(row)
    flags = dedup_flags

    for i, row in enumerate(records, 1):
        row['source_record_id'] = str(i)
    for i, row in enumerate(flags, 1):
        row['flag_id'] = str(i)

    write_csv('sources.csv', sources, source_fields)
    write_csv('source_profiles.csv', profiles, profile_fields)
    write_csv('accounts.csv', accounts, account_fields)
    write_csv('source_records.csv', records, record_fields)
    write_csv('flags.csv', flags, flag_fields)

    print(f'Imported {total} records across {len(SECTIONS)} sections')
    for section in SECTIONS:
        print(f'{section}: {len(parsed[section])}')


if __name__ == '__main__':
    main()
