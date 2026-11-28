-- FinAlly SQLite schema. Every statement is idempotent (IF NOT EXISTS).
-- All tables carry user_id (default 'default') for future multi-user support.
-- watchlist and positions use a composite primary key (user_id, ticker) instead of a UUID
-- (PLAN.md section 13 simplification): one row per ticker per user, simple upserts.
-- Timestamps are ISO-8601 UTC strings written by the application.

CREATE TABLE IF NOT EXISTS users_profile (
    id           TEXT PRIMARY KEY DEFAULT 'default',
    cash_balance REAL NOT NULL DEFAULT 10000.0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id  TEXT NOT NULL DEFAULT 'default' REFERENCES users_profile(id) ON DELETE CASCADE,
    ticker   TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    user_id    TEXT NOT NULL DEFAULT 'default' REFERENCES users_profile(id) ON DELETE CASCADE,
    ticker     TEXT NOT NULL,
    quantity   REAL NOT NULL,
    avg_cost   REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default' REFERENCES users_profile(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    REAL NOT NULL,
    price       REAL NOT NULL,
    executed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_user_time ON trades (user_id, executed_at);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default' REFERENCES users_profile(id) ON DELETE CASCADE,
    total_value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_time ON portfolio_snapshots (user_id, recorded_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default' REFERENCES users_profile(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    actions    TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_user_time ON chat_messages (user_id, created_at);
