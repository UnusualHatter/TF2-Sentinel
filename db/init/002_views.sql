CREATE VIEW v_account_summary AS
SELECT
    a.steamid64,
    a.steam3,
    a.first_observed_at,
    a.last_observed_at,
    count(DISTINCT f.source_id) FILTER (WHERE f.active) AS source_count,
    array_agg(DISTINCT f.flag ORDER BY f.flag) FILTER (WHERE f.active) AS flags,
    count(DISTINCT e.evidence_id) AS evidence_count,
    CASE
        WHEN bool_or(f.active AND f.flag = 'cheater') THEN 'flagged_cheater'
        WHEN bool_or(f.active AND f.flag = 'suspicious') THEN 'suspicious'
        WHEN bool_or(f.active AND f.flag = 'exploiter') THEN 'flagged_exploiter'
        ELSE 'other'
    END AS aggregate_status
FROM accounts a
LEFT JOIN flags f ON f.steamid64 = a.steamid64
LEFT JOIN evidence e ON e.steamid64 = a.steamid64
GROUP BY a.steamid64, a.steam3, a.first_observed_at, a.last_observed_at;

CREATE VIEW v_latest_alias AS
SELECT DISTINCT ON (steamid64)
    steamid64, player_name, observed_at, source_id
FROM aliases
ORDER BY steamid64, observed_at DESC NULLS LAST, alias_id DESC;

CREATE VIEW v_account_detail AS
SELECT
    s.*,
    la.player_name AS latest_name,
    la.observed_at AS latest_name_observed_at
FROM v_account_summary s
LEFT JOIN v_latest_alias la USING (steamid64);

CREATE VIEW v_south_america_bans AS
SELECT
    b.*, srv.name AS server_name, srv.region, srv.country_code
FROM bans b
JOIN servers srv USING (server_id)
WHERE lower(srv.region) IN ('south america','south-america','sa','latam');

CREATE VIEW v_latest_review AS
SELECT DISTINCT ON (steamid64)
    review_id, steamid64, verdict, reason, reviewer, evidence_url, reviewed_at
FROM reviews
WHERE superseded_by IS NULL
ORDER BY steamid64, reviewed_at DESC, review_id DESC;

CREATE VIEW v_effective_account AS
SELECT
    d.*,
    lr.verdict AS manual_verdict,
    lr.reason AS manual_review_reason,
    lr.reviewed_at AS manual_reviewed_at,
    CASE
        WHEN lr.verdict = 'cheater' THEN 'reviewed_cheater'
        WHEN lr.verdict = 'bot' THEN 'reviewed_bot'
        WHEN lr.verdict = 'suspicious' THEN 'reviewed_suspicious'
        WHEN lr.verdict = 'clear' THEN 'reviewed_clear'
        WHEN lr.verdict = 'unknown' THEN 'reviewed_unknown'
        ELSE d.aggregate_status
    END AS effective_status
FROM v_account_detail d
LEFT JOIN v_latest_review lr USING (steamid64);
