# TF2 Sentinel

TF2 Sentinel is a searchable community database that combines public TF2 cheater lists, server bans, league bans, reviewed reports, and other moderation sources.

**Website:** https://unusualhatter.github.io/TF2-Sentinel/

**Current snapshot:** 36,307 SteamIDs · 54,317 source records · 95 sources · updated August 19, 2026.

## Database

The database is normalized by SteamID64 and keeps the original source for each entry.

Each account has a confidence score based on the strength and independence of its sources. Multiple copies or mirrors of the same list do not count as separate evidence.

The score is meant to show how strongly an account is corroborated across available sources, not act as a permanent verdict.

## Files

- `docs/` — GitHub Pages website and public JSON data
- `data/normalized/` — normalized database exports
- `data/reference/` — server and reference data
- `db/init/` — PostgreSQL schema and database seed
- `scripts/` — the pipeline that builds the two above from upstream sources

Upstream lists are not re-hosted here. Each source keeps its original URL in [SOURCES.md](SOURCES.md) and in `docs/data/sources.json`.

## Updating the database

The scripts in `scripts/` download new ban lists, add them to
`data/normalized/`, and rebuild everything generated from it: the
confidence scores, the website's JSON files and the source table in
`SOURCES.md`. They need only Python 3.10 or newer, with nothing to
install.

[scripts/README.md](scripts/README.md) explains how to run them and how to
add a new source.

The confidence formula exists twice: in `db/init/005_confidence_views.sql`
for anyone querying the data in PostgreSQL, and in
`scripts/recompute_confidence.py` so the site can be rebuilt without a
database. The two are checked against each other and must always be
changed together.

## Public data

Apps and tools can use:

- `docs/data/accounts.json`
- `docs/data/sources.json`
- `docs/data/servers.json`
- `docs/data/meta.json`

Accounts are identified by `steamid64`.

## Sources

Source information and confidence treatment are documented in [SOURCES.md](SOURCES.md).

TF2 Sentinel only stores public game/account identifiers and public moderation information. Private personal information and doxxing material are not part of the database.

Public lists can contain mistakes or outdated information. Corrections should preferably be made at the original source and reflected in later database updates.