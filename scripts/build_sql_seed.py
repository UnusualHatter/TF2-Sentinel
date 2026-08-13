#!/usr/bin/env python3
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'normalized'
OUT = ROOT / 'db' / 'init'


def read(name):
    with (DATA / name).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def q(value):
    if value is None or value == '':
        return 'NULL'
    return "'" + str(value).replace("'", "''") + "'"


def q_text(value):
    return q(value if value is not None else '')


def q_json(value):
    return f'{q(value or "{}") }::jsonb'


def q_ts(value):
    return 'NULL' if not value else f'{q(value)}::timestamptz'


def q_date(value):
    return 'NULL' if not value else f'{q(value)}::date'


def boolean(value):
    return 'true' if str(value).lower() == 'true' else 'false'


def build_seed():
    lines = ['BEGIN;']

    for r in read('sources.csv'):
        lines.append(
            'INSERT INTO sources '
            '(source_id,slug,name,source_type,upstream_repo,update_url,authors,scope_region,description,source_file) VALUES '
            f"({r['source_id']},{q_text(r['slug'])},{q_text(r['name'])},{q_text(r['source_type'])},{q(r['upstream_repo'])},{q(r['update_url'])},{q_json(r['authors'])},{q_text(r['scope_region'])},{q_text(r['description'])},{q(r['source_file'])});"
        )

    for r in read('accounts.csv'):
        lines.append(
            'INSERT INTO accounts '
            '(steamid64,account_id,steam3,first_observed_at,last_observed_at) VALUES '
            f"({r['steamid64']},{r['account_id']},{q_text(r['steam3'])},{q_ts(r['first_observed_at'])},{q_ts(r['last_observed_at'])});"
        )

    for r in read('source_records.csv'):
        lines.append(
            'INSERT INTO source_records '
            '(source_record_id,source_id,steamid64,raw_steam_id,record_index,normalization_note,record_hash,raw_record) VALUES '
            f"({r['source_record_id']},{r['source_id']},{r['steamid64']},{q_text(r['raw_steam_id'])},{r['record_index']},{q_text(r['normalization_note'])},{q_text(r['record_hash'])},{q_json(r['raw_record'])});"
        )

    for r in read('flags.csv'):
        lines.append(
            'INSERT INTO flags '
            '(flag_id,steamid64,source_id,flag,review_status,active,observed_at) VALUES '
            f"({r['flag_id']},{r['steamid64']},{r['source_id']},{q_text(r['flag'])},{q_text(r['review_status'])},{boolean(r['active'])},{q_ts(r['observed_at'])});"
        )

    for r in read('aliases.csv'):
        lines.append(
            'INSERT INTO aliases '
            '(alias_id,steamid64,source_id,player_name,observed_at) VALUES '
            f"({r['alias_id']},{r['steamid64']},{r['source_id']},{q_text(r['player_name'])},{q_ts(r['observed_at'])});"
        )

    for r in read('evidence.csv'):
        lines.append(
            'INSERT INTO evidence '
            '(evidence_id,steamid64,source_id,evidence_type,content,observed_at) VALUES '
            f"({r['evidence_id']},{r['steamid64']},{r['source_id']},{q_text(r['evidence_type'])},{q_text(r['content'])},{q_ts(r['observed_at'])});"
        )

    lines.append('COMMIT;')
    (OUT / '003_seed.sql').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def build_profiles():
    lines = [
        'BEGIN;',
        'CREATE TABLE IF NOT EXISTS source_profiles (',
        '    source_id bigint PRIMARY KEY REFERENCES sources(source_id) ON DELETE CASCADE,',
        '    base_weight numeric(5,2) NOT NULL CHECK (base_weight >= 0 AND base_weight <= 100),',
        "    evidence_class text NOT NULL DEFAULT '',",
        "    independence_group text NOT NULL DEFAULT '',",
        '    counts_toward_confidence boolean NOT NULL DEFAULT true,',
        '    is_mirror boolean NOT NULL DEFAULT false,',
        "    assessment_method text NOT NULL DEFAULT '',",
        '    last_verified date,',
        "    notes text NOT NULL DEFAULT ''",
        ');',
    ]

    for r in read('source_profiles.csv'):
        lines.append(
            'INSERT INTO source_profiles '
            '(source_id,base_weight,evidence_class,independence_group,counts_toward_confidence,is_mirror,assessment_method,last_verified,notes) VALUES '
            f"({r['source_id']},{r['base_weight']},{q_text(r['evidence_class'])},{q_text(r['independence_group'])},{boolean(r['counts_toward_confidence'])},{boolean(r['is_mirror'])},{q_text(r['assessment_method'])},{q_date(r['last_verified'])},{q_text(r['notes'])}) "
            'ON CONFLICT (source_id) DO UPDATE SET '
            'base_weight=EXCLUDED.base_weight,evidence_class=EXCLUDED.evidence_class,independence_group=EXCLUDED.independence_group,'
            'counts_toward_confidence=EXCLUDED.counts_toward_confidence,is_mirror=EXCLUDED.is_mirror,'
            'assessment_method=EXCLUDED.assessment_method,last_verified=EXCLUDED.last_verified,notes=EXCLUDED.notes;'
        )

    lines.append('COMMIT;')
    (OUT / '004_source_catalog.sql').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    build_seed()
    build_profiles()
    print('SQL seed files rebuilt')


if __name__ == '__main__':
    main()
