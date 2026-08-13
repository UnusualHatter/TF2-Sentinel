# TF2 Sentinel

TF2 Sentinel is a searchable community database that combines public TF2 cheater lists, server bans, league bans, reviewed reports, and other moderation sources.

**Website:** https://unusualhatter.github.io/TF2-Sentinel/

**Current snapshot:** 21,966 SteamIDs · 32,798 source records · 79 sources · updated August 13, 2026.

## Database

The database is normalized by SteamID64 and keeps the original source for each entry.

Each account has a confidence score based on the strength and independence of its sources. Multiple copies or mirrors of the same list do not count as separate evidence.

The score is meant to show how strongly an account is corroborated across available sources, not act as a permanent verdict.

## Files

- `docs/` — GitHub Pages website and public JSON data
- `data/normalized/` — normalized database exports
- `data/reference/` — server and reference data
- `db/init/` — PostgreSQL schema and database seed

Upstream lists are not re-hosted here. Each source keeps its original URL in [SOURCES.md](SOURCES.md) and in `docs/data/sources.json`.

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