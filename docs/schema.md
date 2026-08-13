# Data model

The normalized CSV data and PostgreSQL schema use the same basic model.

- `accounts` — one canonical row per SteamID64.
- `aliases` — names observed by a source, optionally with a timestamp.
- `sources` — upstream source catalog.
- `source_profiles` — confidence weight, independence group and assessment rules for each source.
- `source_records` — raw imported source records kept for provenance.
- `flags` — classifications asserted by a source (`cheater`, `bot`, `suspicious`, `watched`, `exploiter`, and related values). `server_ban` records a public server ban whose stated reason is not a cheating determination, and `clear` records a source stating the account is legitimate; neither carries confidence weight.
- `evidence` — public proof/note/ban-reason material kept separately from classifications.
- `reviews` — optional local moderation decisions that can override imported state without destroying provenance.
- `servers` / `bans` — PostgreSQL tables for public community-server moderation records.

## Confidence

Only active flags from sources marked `counts_toward_confidence=true` contribute. Each source has an `independence_group`; if several imported or mirrored sources belong to the same family, only the strongest contribution from that family counts.

Each flag has a fixed multiplier defined in `db/init/005_confidence_views.sql`. `server_ban` and `clear` are explicitly zero, so a conduct ban, an alt-account detection or a legitimate-player listing is kept for provenance without raising the score.

The score is designed to summarize corroboration, not to convert every imported list entry into a confirmed verdict.

## Public view

The static site consumes generated files under `docs/data/`. PostgreSQL consumers should generally start with `v_account_detail` or `v_effective_account` instead of reconstructing source joins themselves.
