#!/usr/bin/env python3
import csv
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'data' / 'normalized'
P = ROOT / 'data' / 'public'


def read(name):
    with (D / name).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def main():
    accounts = read('accounts.csv')
    flags = read('flags.csv')
    sources = read('sources.csv')
    profiles = read('source_profiles.csv')
    aliases = read('aliases.csv')
    evidence = read('evidence.csv')
    steam_profiles = read('steam_profiles.csv') if (D / 'steam_profiles.csv').exists() else []

    src = {r['source_id']: r for r in sources}
    prof = {r['source_id']: r for r in profiles}
    steam = {r['steamid64']: r for r in steam_profiles}

    latest = {}
    for r in aliases:
        key = (r.get('observed_at') or '', int(r['alias_id']))
        if r['steamid64'] not in latest or key > latest[r['steamid64']][0]:
            latest[r['steamid64']] = (key, r.get('player_name') or '')

    ev = Counter(r['steamid64'] for r in evidence)
    multipliers = {
        'cheater': 1.0,
        'bot': 1.0,
        'exploiter': 0.70,
        'suspicious': 0.45,
        'watched': 0.20,
        'association': 0.10,
        'cheater_supporter': 0.10,
        'clear': 0.0,
        'legit': 0.0,
    }

    by = defaultdict(list)
    source_sets = defaultdict(set)
    all_flags = defaultdict(set)

    for r in flags:
        if r.get('active', '').lower() != 'true':
            continue
        source_sets[r['steamid64']].add(r['source_id'])
        all_flags[r['steamid64']].add(r['flag'])
        p = prof.get(r['source_id'])
        if not p or p.get('counts_toward_confidence', '').lower() != 'true':
            continue
        multiplier = multipliers.get(r['flag'].lower(), 0.20)
        contribution = min(99.5, float(p['base_weight']) * multiplier)
        if contribution > 0:
            by[r['steamid64']].append((p['independence_group'], contribution, r['source_id'], r['flag']))

    out = []
    for a in accounts:
        steamid64 = a['steamid64']
        vals = by.get(steamid64, [])
        best = {}
        for group, contribution, source_id, flag in vals:
            if group not in best or contribution > best[group][0]:
                best[group] = (contribution, source_id, flag)

        product = 1.0
        for contribution, _, _ in best.values():
            product *= 1 - contribution / 100
        score = round((1 - product) * 100, 1) if best else 0.0

        if score >= 95:
            tier = 'very_high'
        elif score >= 80:
            tier = 'high'
        elif score >= 60:
            tier = 'medium'
        elif score >= 30:
            tier = 'low'
        elif score > 0:
            tier = 'very_low'
        else:
            tier = 'unscored'

        strongest = sorted(best.items(), key=lambda kv: -kv[1][0])[:8]
        strongest_ids = [v[1] for _, v in strongest]
        strongest_slugs = [src[sid]['slug'] for sid in strongest_ids]
        strongest_names = [src[sid]['name'] for sid in strongest_ids]
        all_source_ids = sorted(source_sets.get(steamid64, set()), key=int)
        all_source_slugs = [src[sid]['slug'] for sid in all_source_ids if sid in src]
        all_source_names = [src[sid]['name'] for sid in all_source_ids if sid in src]
        sp = steam.get(steamid64, {})

        out.append({
            'steamid64': steamid64,
            'steam3': a['steam3'],
            'latest_name': latest.get(steamid64, (None, ''))[1],
            'steam_persona_name': sp.get('personaname', ''),
            'steam_profile_url': sp.get('profileurl') or f'https://steamcommunity.com/profiles/{steamid64}/',
            'steamhistory_url': f'https://steamhistory.net/id/{steamid64}',
            'avatar_url': sp.get('avatar_medium') or sp.get('avatar') or '',
            'avatar_full_url': sp.get('avatar_full') or '',
            'confidence_score': f'{score:.1f}',
            'confidence_tier': tier,
            'independent_source_groups': len(best),
            'source_count': len(all_source_ids),
            'raw_source_signals': len(vals),
            'evidence_count': ev[steamid64],
            'flags': ';'.join(sorted(all_flags.get(steamid64, set()))),
            'primary_source': strongest_slugs[0] if strongest_slugs else '',
            'primary_source_name': strongest_names[0] if strongest_names else '',
            'strongest_sources': ';'.join(strongest_slugs),
            'strongest_source_names': ';'.join(strongest_names),
            'all_sources': ';'.join(all_source_slugs),
            'all_source_names': ';'.join(all_source_names),
        })

    out.sort(key=lambda r: (-float(r['confidence_score']), -int(r['independent_source_groups']), int(r['steamid64'])))

    D.mkdir(parents=True, exist_ok=True)
    P.mkdir(parents=True, exist_ok=True)
    (ROOT / 'docs' / 'data').mkdir(parents=True, exist_ok=True)
    fields = list(out[0])

    for path in [D / 'confidence.csv', P / 'accounts.csv']:
        with path.open('w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(out)

    payload = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    (P / 'accounts.json').write_text(payload, encoding='utf-8')
    (ROOT / 'docs' / 'data' / 'accounts.json').write_text(payload, encoding='utf-8')

    source_export = []
    for row in sources:
        merged = dict(row)
        merged.update(prof.get(row['source_id'], {}))
        source_export.append(merged)
    source_payload = json.dumps(source_export, ensure_ascii=False, separators=(',', ':'))
    (P / 'sources.json').write_text(source_payload, encoding='utf-8')
    (ROOT / 'docs' / 'data' / 'sources.json').write_text(source_payload, encoding='utf-8')

    flags_by_account = defaultdict(set)
    sources_by_account = defaultdict(set)
    for row in flags:
        if row.get('active', '').lower() != 'true':
            continue
        flags_by_account[row['steamid64']].add(row['flag'])
        sources_by_account[row['steamid64']].add(row['source_id'])

    account_summary = []
    for a in accounts:
        sid = a['steamid64']
        values = flags_by_account.get(sid, set())
        if 'cheater' in values or 'bot' in values:
            status = 'flagged_cheater'
        elif 'exploiter' in values:
            status = 'flagged_exploiter'
        elif 'suspicious' in values or 'watched' in values:
            status = 'suspicious'
        elif values and values <= {'clear', 'legit'}:
            status = 'clear'
        elif values:
            status = 'flagged'
        else:
            status = 'unflagged'
        alias_info = latest.get(sid, (('', 0), ''))
        account_summary.append({
            'steamid64': sid,
            'steam3': a['steam3'],
            'aggregate_status': status,
            'source_count': len(sources_by_account.get(sid, set())),
            'flags': ';'.join(sorted(values)),
            'evidence_count': ev[sid],
            'latest_name': alias_info[1],
            'latest_name_observed_at': alias_info[0][0] if alias_info[0] else '',
            'first_observed_at': a.get('first_observed_at', ''),
            'last_observed_at': a.get('last_observed_at', ''),
        })
    account_summary.sort(key=lambda r: int(r['steamid64']))
    summary_fields = list(account_summary[0])
    with (D / 'account_summary.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=summary_fields)
        w.writeheader()
        w.writerows(account_summary)

    tiers = Counter(r['confidence_tier'] for r in out)
    now = datetime.now(ZoneInfo('America/Sao_Paulo'))
    summary = {
        'unique_accounts': len(accounts),
        'source_records': len(read('source_records.csv')),
        'flags': len(flags),
        'evidence_rows': len(evidence),
        'registered_sources': len(sources),
        'data_bearing_seed_sources': len({r['source_id'] for r in read('source_records.csv')}),
        'confidence_tiers': {k: tiers.get(k, 0) for k in ['very_high', 'high', 'medium', 'low', 'very_low', 'unscored']},
        'generated_at': now.isoformat(timespec='seconds'),
    }
    (D / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    meta = {
        'last_database_update': now.date().isoformat(),
        'last_database_update_display': f'{now.strftime("%B")} {now.day}, {now.year}',
        'generated_at': now.isoformat(timespec='seconds'),
        'timezone': 'America/Sao_Paulo',
        'unique_accounts': len(accounts),
        'registered_sources': len(sources),
    }
    meta_payload = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
    (P / 'meta.json').write_text(meta_payload, encoding='utf-8')
    (ROOT / 'docs' / 'data' / 'meta.json').write_text(meta_payload, encoding='utf-8')

    print(f'Wrote {len(out)} accounts and {len(source_export)} sources')


if __name__ == '__main__':
    main()
