CREATE OR REPLACE VIEW v_confidence_contributions AS
SELECT
    f.steamid64,
    f.source_id,
    sp.independence_group,
    f.flag,
    sp.base_weight,
    LEAST(99.5,
        sp.base_weight * CASE lower(f.flag)
            WHEN 'cheater' THEN 1.00
            WHEN 'bot' THEN 1.00
            WHEN 'exploiter' THEN 0.70
            WHEN 'suspicious' THEN 0.45
            WHEN 'association' THEN 0.10
            WHEN 'cheater_supporter' THEN 0.10
            -- Imported for provenance only: a conduct/alt-account ban or a
            -- source stating the account is clear must not raise confidence.
            WHEN 'server_ban' THEN 0.00
            WHEN 'clear' THEN 0.00
            ELSE 0.20
        END
    ) AS contribution
FROM flags f
JOIN source_profiles sp USING (source_id)
WHERE f.active AND sp.counts_toward_confidence;

CREATE OR REPLACE VIEW v_confidence_independent AS
SELECT DISTINCT ON (steamid64, independence_group)
    steamid64, independence_group, source_id, flag, base_weight, contribution
FROM v_confidence_contributions
ORDER BY steamid64, independence_group, contribution DESC, source_id;

CREATE OR REPLACE VIEW v_account_confidence AS
WITH grouped AS (
    SELECT
        steamid64,
        count(*) AS independent_source_groups,
        round((100 * (1 - exp(sum(ln(1 - contribution / 100.0)))))::numeric, 1) AS confidence_score
    FROM v_confidence_independent
    GROUP BY steamid64
)
SELECT
    a.steamid64,
    a.steam3,
    coalesce(g.confidence_score, 0.0) AS confidence_score,
    CASE
        WHEN coalesce(g.confidence_score,0) >= 95 THEN 'very_high'
        WHEN coalesce(g.confidence_score,0) >= 80 THEN 'high'
        WHEN coalesce(g.confidence_score,0) >= 60 THEN 'medium'
        WHEN coalesce(g.confidence_score,0) >= 30 THEN 'low'
        WHEN coalesce(g.confidence_score,0) > 0 THEN 'very_low'
        ELSE 'unscored'
    END AS confidence_tier,
    coalesce(g.independent_source_groups,0) AS independent_source_groups
FROM accounts a
LEFT JOIN grouped g USING (steamid64);
