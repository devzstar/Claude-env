-- Clipping pipeline — SQLite schema (v1)
-- Source of truth for every stage. Timestamps are ISO-8601 UTC text.
-- Money is stored as REAL in the campaign's currency (USD by default).

PRAGMA foreign_keys = ON;

-- Added beyond PLAN.md §4: Whop must be linked BEFORE the first post (PLAN §2),
-- so accounts are first-class and posts reference them.
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY,
    platform        TEXT NOT NULL CHECK (platform IN ('tiktok','youtube','instagram')),
    handle          TEXT NOT NULL,
    whop_linked_at  TEXT,                       -- NULL = not linked yet
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (platform, handle)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    url              TEXT,
    rate_per_1k      REAL NOT NULL CHECK (rate_per_1k >= 0),
    budget_total     REAL,
    budget_left      REAL,
    min_payout       REAL,
    max_payout       REAL,
    currency         TEXT NOT NULL DEFAULT 'USD',
    platforms        TEXT NOT NULL DEFAULT 'tiktok,youtube,instagram', -- comma list
    required_tags    TEXT,                      -- comma list; checked against captions
    rules_notes      TEXT,
    source_provided  INTEGER NOT NULL DEFAULT 1 CHECK (source_provided IN (0,1)),
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','dead')),
    joined_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    budget_checked_at TEXT                      -- last time budget_left was refreshed
);

CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY,
    campaign_id  INTEGER NOT NULL REFERENCES campaigns(id),
    path_or_url  TEXT NOT NULL,
    duration_s   REAL,
    added_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS clips (
    id              INTEGER PRIMARY KEY,
    campaign_id     INTEGER NOT NULL REFERENCES campaigns(id),
    source_id       INTEGER REFERENCES sources(id),
    start_s         REAL,
    end_s           REAL,
    hook_text       TEXT,
    file_path       TEXT,
    virality_score  REAL,
    status          TEXT NOT NULL DEFAULT 'candidate'
                    CHECK (status IN ('candidate','approved','rejected','posted')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    CHECK (end_s IS NULL OR start_s IS NULL OR end_s > start_s)
);

CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY,
    clip_id     INTEGER NOT NULL REFERENCES clips(id),
    platform    TEXT NOT NULL CHECK (platform IN ('tiktok','youtube','instagram')),
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    post_url    TEXT NOT NULL UNIQUE,
    caption     TEXT,
    posted_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- One submission per post; resubmits update the row.
CREATE TABLE IF NOT EXISTS submissions (
    id             INTEGER PRIMARY KEY,
    post_id        INTEGER NOT NULL UNIQUE REFERENCES posts(id),
    submitted_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','approved','rejected')),
    reject_reason  TEXT,
    decided_at     TEXT
);

CREATE TABLE IF NOT EXISTS view_snaps (
    id               INTEGER PRIMARY KEY,
    post_id          INTEGER NOT NULL REFERENCES posts(id),
    taken_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    views            INTEGER NOT NULL CHECK (views >= 0),
    likes            INTEGER CHECK (likes IS NULL OR likes >= 0),
    source           TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('api','manual')),
    screenshot_path  TEXT
);

CREATE TABLE IF NOT EXISTS payouts (
    id           INTEGER PRIMARY KEY,
    campaign_id  INTEGER NOT NULL REFERENCES campaigns(id),
    amount       REAL NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'USD',
    paid_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS time_log (
    id        INTEGER PRIMARY KEY,
    date      TEXT NOT NULL DEFAULT (date('now')),
    minutes   INTEGER NOT NULL CHECK (minutes > 0),
    activity  TEXT NOT NULL CHECK (activity IN ('scout','review','post','admin','edit'))
);

CREATE INDEX IF NOT EXISTS idx_clips_campaign   ON clips(campaign_id);
CREATE INDEX IF NOT EXISTS idx_posts_clip       ON posts(clip_id);
CREATE INDEX IF NOT EXISTS idx_snaps_post_taken ON view_snaps(post_id, taken_at);
