# Holiday CheaterDB

Public TF2 moderation-signal database with PostgreSQL support, source provenance, deduplication, confidence scoring, South America coverage, MvM reputation sources, and static GitHub Pages exports.

## Current snapshot

- Last database update: August 12, 2026
- 19,239 unique Steam accounts
- 29,436 imported source records
- 29,530 imported flags
- 11,489 evidence/source-note rows
- 36 data-bearing seed sources
- 70 registered public sources and source families
- confidence tiers: very_high=1,402, high=10,327, medium=3,402, low=112, very_low=3,918, unscored=78

A confidence score is a source-corroboration estimate, not a factual declaration about a person. The database stores public Steam identifiers and public moderation evidence only.

## Confidence model

Each source has a base weight and an `independence_group`. Multiple copies, mirrors, aggregators, or derived lists from the same underlying source family only contribute once. Flag type then scales the source weight.

| Signal | Multiplier |
|---|---:|
| cheater / bot | 1.00 |
| exploiter | 0.70 |
| suspicious | 0.45 |
| association / cheater supporter | 0.10 |
| other imported flag | 0.20 |

Independent contributions are combined with diminishing returns. Tiers are `very_high` (95+), `high` (80-94.9), `medium` (60-79.9), `low` (30-59.9), `very_low` (0-29.9), and `unscored`.

Use `data/normalized/confidence.csv` or PostgreSQL view `v_account_confidence`.

## GitHub / GitHub Pages

The repository includes a dependency-free static viewer in `docs/`.

GitHub Pages setup:

1. Push the repository to GitHub.
2. Open repository **Settings → Pages**.
3. Choose **Deploy from a branch**.
4. Select the default branch and `/docs`.

Machine-readable public exports:

- `data/public/accounts.json`
- `data/public/accounts.csv`
- `data/public/sources.json`
- `data/public/meta.json`
- `docs/data/accounts.json`
- `docs/data/sources.json`
- `docs/data/meta.json`
- `docs/API.md` (field contract for consumers)

These files can be consumed directly through GitHub raw URLs or GitHub Pages.

The Pages viewer displays SteamID64, confidence level, Steam profile link, source provenance, and SteamHistory lookup. Steam avatars and current persona names are populated by `scripts/enrich_steam_profiles.py`. For the included GitHub Actions refresh workflow, add a repository secret named `STEAM_WEB_API_KEY`.

## PostgreSQL

```bash
cp .env.example .env
docker compose up -d
```

Initialization order:

```text
db/init/001_schema.sql
db/init/002_views.sql
db/init/003_seed.sql
db/init/004_source_catalog.sql
db/init/005_confidence_views.sql
```

Query confidence:

```sql
SELECT *
FROM v_account_confidence
ORDER BY confidence_score DESC, steamid64;
```

## Source coverage

`THIRD_PARTY_SOURCES.md` contains the full registered source catalog. It includes TF2 Bot Detector lists, competitive league bans, SourceBans communities, South American communities, MvM reputation platforms, historical bot lists, and Valve ban signals.

South America-specific registered sources include Serv dos Brother, Vovô Fortress and Brasil Fortress. MvM-specific sources include MetalStats, MvM Lobby and Tacobot report history; these are weighted as community reputation/report signals rather than convictions.

## Updating

Rebuild confidence/public exports after changing normalized CSV data:

```bash
python scripts/rebuild_confidence.py
```

Validate normalized data:

```bash
python scripts/validate_data.py
```

Enrich existing SteamIDs through the public Rent-a-Medic lookup API:

```bash
python scripts/sync_rentamedic.py
```

SourceBans scraping/import helpers are in `scripts/scrape_sourcebans.py` and `scripts/import_sourcebans.py`.

## Data policy

Do not add private real-world identity data, credentials, IP-address dumps, payment information, private cheat-provider customer records, doxxing material, or unrelated personal information. Keep source URLs, public Steam identifiers, public aliases, public moderation reasons, public demos/evidence links, and appeal/reversal state.
