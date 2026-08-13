![TF2 Sentinel](docs/assets/sentinel-banner.png)

# TF2 Sentinel

TF2 Sentinel is a community-maintained index that combines public TF2 moderation lists, league bans, server bans, reviewed reports and historical player-list data into one searchable SteamID64 dataset.

**Site:** https://unusualhatter.github.io/TF2-Sentinel/

**Current bundled snapshot:** 19,272 SteamIDs · 29,471 source records · 78 registered sources · updated August 13, 2026.

The project keeps the upstream source for every imported signal and groups related mirrors so the same underlying list does not count several times toward confidence. The score is a **corroboration score**, not a permanent verdict: public lists can be wrong, old or later reversed.

## What is in the repository

- `docs/` — the static GitHub Pages viewer and its public JSON snapshot.
- `data/normalized/` — canonical CSV tables used to build the snapshot and PostgreSQL seed.
- `data/raw/` — retained upstream/supplied list snapshots; every normalized import also keeps its raw record in `source_records.csv`.
- `data/reference/` — server/reference catalogs that are not themselves cheater verdicts.
- `db/init/` — PostgreSQL schema, views and generated seed.
- `scripts/` — maintenance tools for refreshing public sources, Steam profile metadata and generated exports.
- `config/sources.json` — configured public update endpoints.

The Python files are maintenance tools. GitHub Pages does not run Python and the site can be browsed directly from `docs/`; the scripts are kept because removing them would make future database updates difficult to reproduce.

## Confidence

Each source has a base weight and an independence group. A source flag is multiplied by the strength of the classification (`cheater`, `bot`, `suspicious`, `watched`, and so on), and only the strongest signal in an independence group counts. This prevents mirrors or compiled copies of the same database from inflating a player's score.

The site shows the main counted source in the table. Use the `+N` control to see the rest of that account's source history without expanding the table columns.

## Public data

Static consumers can use:

- `docs/data/accounts.json`
- `docs/data/sources.json`
- `docs/data/servers.json`
- `docs/data/meta.json`

These same files power GitHub Pages, so there is only one static copy in the repository. Accounts should be keyed by `steamid64`; source definitions should be keyed by `slug`.

## Updating

Install the maintenance dependencies:

```bash
python -m pip install -r requirements.txt
```

Refresh configured TF2BD-style lists:

```bash
python scripts/sync_tf2bd.py
```

Refresh explicit cheating bans from configured public SourceBans instances:

```bash
python scripts/sync_sourcebans.py
```

Refresh Steam names and avatar URLs with a Steam Web API key:

```bash
STEAM_WEB_API_KEY=... python scripts/enrich_steam_profiles.py
python scripts/rebuild_confidence.py
python scripts/build_sql_seed.py
python scripts/validate_data.py
```

A slower keyless public-profile mode is also available:

```bash
python scripts/enrich_steam_profiles.py --xml
```

Valve documents the Steam Community XML profile endpoint as deprecated, so the Web API route is preferred when a key is available.

## PostgreSQL

Copy the example environment file and start PostgreSQL:

```bash
cp .env.example .env
docker compose up -d
```

Default local connection:

```text
postgresql://tf2sentinel:change-me@localhost:5432/tf2sentinel
```

## Sources and corrections

The complete source catalog and scoring treatment are documented in [SOURCES.md](SOURCES.md). Sources that are mirrors, aggregators, association lists or identity-history services can be retained for provenance without being treated as independent proof.

TF2 Sentinel stores public game/account identifiers and public moderation evidence. It is not intended for private personal information, credentials, addresses or doxxing material.

If an upstream moderation record was reversed or a public list contains a false positive, the best correction is to fix the upstream record and then refresh the corresponding source. Local review data can also override imported state without deleting source history.
