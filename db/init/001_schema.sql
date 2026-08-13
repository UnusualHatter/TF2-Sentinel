-- Holiday CheaterDB - PostgreSQL schema
-- Labels in this database are source assertions, not independent findings.

CREATE TABLE sources (
    source_id       bigint PRIMARY KEY,
    slug            text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    name            text NOT NULL,
    source_type     text NOT NULL,
    upstream_repo   text,
    update_url      text,
    authors         jsonb NOT NULL DEFAULT '[]'::jsonb,
    scope_region    text NOT NULL DEFAULT 'unknown',
    description     text NOT NULL DEFAULT '',
    source_file     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE accounts (
    steamid64           bigint PRIMARY KEY,
    account_id          bigint NOT NULL,
    steam3              text NOT NULL,
    first_observed_at   timestamptz,
    last_observed_at    timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT steamid64_public_individual_range CHECK (
        steamid64 BETWEEN 76561197960265728 AND 76561202255233023
    ),
    CONSTRAINT account_id_range CHECK (account_id BETWEEN 0 AND 4294967295),
    CONSTRAINT steamid64_matches_account_id CHECK (steamid64 = 76561197960265728 + account_id)
);
CREATE UNIQUE INDEX accounts_account_id_uq ON accounts(account_id);

CREATE TABLE source_records (
    source_record_id   bigint PRIMARY KEY,
    source_id          bigint NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    steamid64          bigint NOT NULL REFERENCES accounts(steamid64) ON DELETE CASCADE,
    raw_steam_id       text NOT NULL,
    record_index       integer NOT NULL,
    normalization_note text NOT NULL DEFAULT '',
    record_hash        text NOT NULL UNIQUE,
    raw_record         jsonb NOT NULL,
    imported_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE(source_id, record_index)
);
CREATE INDEX source_records_account_idx ON source_records(steamid64);
CREATE INDEX source_records_source_idx ON source_records(source_id);
CREATE INDEX source_records_raw_gin ON source_records USING gin(raw_record);

CREATE TABLE flags (
    flag_id         bigint PRIMARY KEY,
    steamid64       bigint NOT NULL REFERENCES accounts(steamid64) ON DELETE CASCADE,
    source_id       bigint NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    flag            text NOT NULL,
    review_status   text NOT NULL DEFAULT 'imported'
                    CHECK (review_status IN ('imported','verified','rejected','appealed')),
    active          boolean NOT NULL DEFAULT true,
    observed_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(steamid64, source_id, flag)
);
CREATE INDEX flags_account_idx ON flags(steamid64);
CREATE INDEX flags_flag_idx ON flags(flag) WHERE active;
CREATE INDEX flags_source_idx ON flags(source_id);

CREATE TABLE aliases (
    alias_id        bigint PRIMARY KEY,
    steamid64       bigint NOT NULL REFERENCES accounts(steamid64) ON DELETE CASCADE,
    source_id       bigint NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    player_name     text NOT NULL,
    observed_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX aliases_account_idx ON aliases(steamid64);
CREATE INDEX aliases_name_lower_idx ON aliases(lower(player_name));

CREATE TABLE evidence (
    evidence_id     bigint PRIMARY KEY,
    steamid64       bigint NOT NULL REFERENCES accounts(steamid64) ON DELETE CASCADE,
    source_id       bigint NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    evidence_type   text NOT NULL DEFAULT 'source_note',
    content         text NOT NULL,
    observed_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evidence_account_idx ON evidence(steamid64);
CREATE INDEX evidence_source_idx ON evidence(source_id);

-- Manual/community review is intentionally separate from imported assertions.
CREATE TABLE reviews (
    review_id       bigserial PRIMARY KEY,
    steamid64       bigint NOT NULL REFERENCES accounts(steamid64) ON DELETE CASCADE,
    verdict         text NOT NULL CHECK (verdict IN ('cheater','bot','suspicious','clear','unknown')),
    reason          text NOT NULL DEFAULT '',
    reviewer        text NOT NULL DEFAULT '',
    evidence_url    text,
    reviewed_at     timestamptz NOT NULL DEFAULT now(),
    superseded_by   bigint REFERENCES reviews(review_id)
);
CREATE INDEX reviews_account_idx ON reviews(steamid64, reviewed_at DESC);

CREATE TABLE servers (
    server_id       bigserial PRIMARY KEY,
    name            text NOT NULL,
    region          text NOT NULL DEFAULT 'unknown',
    country_code    char(2),
    sourcebans_url  text,
    notes           text NOT NULL DEFAULT '',
    UNIQUE(name, sourcebans_url)
);

CREATE TABLE bans (
    ban_id              bigserial PRIMARY KEY,
    steamid64           bigint NOT NULL REFERENCES accounts(steamid64) ON DELETE CASCADE,
    server_id           bigint REFERENCES servers(server_id) ON DELETE SET NULL,
    source_id           bigint REFERENCES sources(source_id) ON DELETE SET NULL,
    external_ban_id     text,
    reason              text NOT NULL DEFAULT '',
    admin_name          text NOT NULL DEFAULT '',
    ban_created_at      timestamptz,
    ban_expires_at      timestamptz,
    active              boolean,
    source_url          text,
    raw_record          jsonb NOT NULL DEFAULT '{}'::jsonb,
    imported_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE(server_id, external_ban_id)
);
CREATE INDEX bans_account_idx ON bans(steamid64);
CREATE INDEX bans_server_idx ON bans(server_id);
