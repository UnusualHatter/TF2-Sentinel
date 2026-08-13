# Static data interface

TF2 Sentinel publishes dependency-free JSON under `docs/data/`, suitable for GitHub Pages, raw GitHub URLs or small client integrations.

## `data/accounts.json`

One object per canonical SteamID64.

Important fields:

- `steamid64`, `steam3`
- `latest_name`, `steam_persona_name`
- `avatar_url` when Steam enrichment has been run; profile/history links can be constructed from `steamid64`
- `confidence_score`, `confidence_tier`
- `independent_source_groups`, `source_count`, `raw_source_signals`
- `evidence_count`, `flags`
- `primary_source`, `strongest_sources`, `all_sources`

`primary_source`, `strongest_sources` and `all_sources` contain source slugs. Resolve them against `sources.json` instead of parsing source display text.

## `data/sources.json`

The source catalog plus scoring metadata. Source slugs are stable integration keys. Fields include upstream URL, source type, region, base weight, independence group, whether the source counts toward confidence, mirror state and assessment method.

`short_name` is the compact label used in the account table; `name` is the full catalog label.

## `data/servers.json`

Reference catalog for the South American servers tracked by this snapshot. A server entry is not a moderation assertion. `public_moderation_url` is only present where a public ban system was located.

## `data/meta.json`

Snapshot metadata used by the site: `last_database_update`, `last_database_update_display`, `generated_at`, `timezone`, `unique_accounts`, `source_records`, `registered_sources`, `data_bearing_sources` and `servers_tracked`.

## Stability

Consumers should key accounts by `steamid64` and sources by `slug`. New fields may be added without notice. Display names are allowed to change as source labels are normalized; do not use them as identifiers.
