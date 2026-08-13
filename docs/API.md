# Static data interface

The repository exposes dependency-free machine-readable files suitable for GitHub raw URLs or GitHub Pages.

## Accounts

`data/public/accounts.json` and `docs/data/accounts.json` contain one object per SteamID64.

Fields:

- `steamid64`: canonical SteamID64
- `steam3`: Steam3 form
- `latest_name`: latest public alias observed in the imported data
- `steam_persona_name`: current public Steam persona name when profile enrichment is available
- `steam_profile_url`: public Steam Community profile URL
- `steamhistory_url`: SteamHistory lookup URL for the SteamID64
- `avatar_url`: public Steam avatar URL when profile enrichment is available
- `confidence_score`: 0-100 corroboration score
- `confidence_tier`: `unscored`, `very_low`, `low`, `medium`, `high`, or `very_high`
- `independent_source_groups`: number of independently counted source families
- `raw_source_signals`: number of source signals before de-duplication
- `evidence_count`: stored public evidence/note rows
- `flags`: semicolon-delimited imported classifications
- `strongest_sources`: semicolon-delimited source slugs

## Sources

`data/public/sources.json` and `docs/data/sources.json` expose the source catalog and confidence metadata, including source URL, weight, evidence class, independence group, mirror status, and assessment method.

## Metadata

`data/public/meta.json` and `docs/data/meta.json` expose snapshot metadata used by the GitHub Pages viewer.

Fields:

- `last_database_update`: update date in `YYYY-MM-DD`
- `last_database_update_display`: human-readable update date
- `generated_at`: snapshot generation timestamp
- `timezone`: timezone used for the update date
- `unique_accounts`: number of unique SteamID64 records
- `registered_sources`: number of source catalog entries

## Stability

Consumers should key accounts by `steamid64` and sources by `slug`. New fields may be added without notice; existing field meanings should remain stable.
