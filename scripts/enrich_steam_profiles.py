#!/usr/bin/env python3
import csv
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'normalized'
ACCOUNTS = DATA / 'accounts.csv'
OUT = DATA / 'steam_profiles.csv'
API_URL = 'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/'


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def load_existing():
    if not OUT.exists():
        return {}
    with OUT.open(encoding='utf-8', newline='') as f:
        return {r['steamid64']: r for r in csv.DictReader(f)}


def main():
    key = os.environ.get('STEAM_WEB_API_KEY', '').strip()
    if not key:
        raise SystemExit('STEAM_WEB_API_KEY is required')

    with ACCOUNTS.open(encoding='utf-8', newline='') as f:
        steamids = [r['steamid64'] for r in csv.DictReader(f)]

    profiles = load_existing()
    pending = [sid for sid in steamids if sid not in profiles or not profiles[sid].get('avatar_medium')]

    session = requests.Session()
    session.headers['User-Agent'] = 'Holiday-CheaterDB/1.0'

    for batch in chunks(pending, 100):
        response = session.get(API_URL, params={'key': key, 'steamids': ','.join(batch)}, timeout=30)
        response.raise_for_status()
        returned = {p['steamid']: p for p in response.json().get('response', {}).get('players', [])}
        for sid in batch:
            p = returned.get(sid, {})
            profiles[sid] = {
                'steamid64': sid,
                'personaname': p.get('personaname', ''),
                'profileurl': p.get('profileurl', f'https://steamcommunity.com/profiles/{sid}/'),
                'avatar': p.get('avatar', ''),
                'avatar_medium': p.get('avatarmedium', ''),
                'avatar_full': p.get('avatarfull', ''),
                'community_visibility_state': str(p.get('communityvisibilitystate', '')),
                'last_logoff': str(p.get('lastlogoff', '')),
            }
        time.sleep(0.15)

    fields = ['steamid64', 'personaname', 'profileurl', 'avatar', 'avatar_medium', 'avatar_full', 'community_visibility_state', 'last_logoff']
    with OUT.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for sid in sorted(profiles, key=int):
            w.writerow({k: profiles[sid].get(k, '') for k in fields})

    print(f'Wrote {len(profiles)} Steam profiles')


if __name__ == '__main__':
    main()
