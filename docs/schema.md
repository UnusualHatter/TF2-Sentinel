# Data model

`accounts` contains one canonical Steam account per SteamID64. `source_records` preserves the exact imported record and raw Steam identifier from each upstream list. `flags` stores what each source asserted (`cheater`, `suspicious`, `exploiter`, etc.); imported flags are **not** automatically treated as verified. `aliases` stores source-observed persona names with timestamps. `evidence` stores upstream proof/note strings separately so evidence is not conflated with classification.

`reviews` is for your own later moderation decisions. `servers` and `bans` are designed for South American community-server/SourceBans imports.

The `v_account_detail` view is the safe default query surface. Its `aggregate_status` deliberately uses names such as `flagged_cheater`, not `confirmed_cheater`.

`v_effective_account` overlays the latest manual review on top of imported source flags, so accepted appeals or a `clear` review can be represented without deleting source history.
