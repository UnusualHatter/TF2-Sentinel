-- One account with provenance
SELECT d.*, s.name AS source_name, f.flag, f.review_status
FROM v_account_detail d
LEFT JOIN flags f USING (steamid64)
LEFT JOIN sources s USING (source_id)
WHERE d.steamid64 = 76561198000000000;

-- Accounts flagged by more than one independent imported source
SELECT *
FROM v_effective_account
WHERE source_count >= 2
ORDER BY source_count DESC, steamid64;

-- Suspicious-only records; useful for avoiding overclaiming
SELECT *
FROM v_effective_account
WHERE aggregate_status = 'suspicious'
ORDER BY source_count DESC;

-- South America bans after SourceBans/server imports
SELECT * FROM v_south_america_bans ORDER BY ban_created_at DESC NULLS LAST;
