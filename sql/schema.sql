-- =============================================================
-- schema.sql
-- Compatible with PostgreSQL 13+ and MySQL 8+
--
-- Run once before starting the service:
--   PostgreSQL:  psql -U <user> -d <db> -f schema.sql
--   MySQL:       mysql -u <user> -p <db> < schema.sql
-- =============================================================

-- -------------------------------------------------------------
-- odds_movements
-- One row per price point observed at a point in time.
-- The unique constraint prevents duplicate inserts when the
-- poller restarts and replays the same `last` cursor window.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS odds_movements (
    id            BIGSERIAL PRIMARY KEY,          -- use BIGINT AUTO_INCREMENT for MySQL

    sport         VARCHAR(32)     NOT NULL,        -- 'football' | 'basketball'
    league_id     INT             NOT NULL,
    league_name   VARCHAR(255)    NOT NULL,
    event_id      BIGINT          NOT NULL,
    home_team     VARCHAR(255)    NOT NULL,
    away_team     VARCHAR(255)    NOT NULL,

    market_type   VARCHAR(16)     NOT NULL,        -- 'moneyline' | 'spread' | 'total'
    period        SMALLINT        NOT NULL,        -- 0=full game, 1=1st half, etc.

    price_home    NUMERIC(8,4),                    -- home / over price (decimal odds)
    price_away    NUMERIC(8,4),                    -- away / under price
    price_draw    NUMERIC(8,4),                    -- draw (moneyline only)
    line          NUMERIC(6,2),                    -- spread hdp or total points
    max_bet       NUMERIC(12,2),                   -- maximum stake allowed

    recorded_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Prevent exact duplicate rows (same snapshot already stored)
CREATE UNIQUE INDEX IF NOT EXISTS uq_odds_snapshot
    ON odds_movements (event_id, market_type, period, price_home, price_away, price_draw, line, recorded_at);

-- Fast lookups by event
CREATE INDEX IF NOT EXISTS idx_odds_event
    ON odds_movements (event_id, recorded_at DESC);

-- Fast lookups by sport + time (dashboards, exports)
CREATE INDEX IF NOT EXISTS idx_odds_sport_time
    ON odds_movements (sport, recorded_at DESC);

-- Fast lookups by league
CREATE INDEX IF NOT EXISTS idx_odds_league
    ON odds_movements (league_id, recorded_at DESC);


-- =============================================================
-- MySQL-compatible version (comment out the block above and
-- uncomment this block when targeting MySQL)
-- =============================================================
/*
CREATE TABLE IF NOT EXISTS odds_movements (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    sport         VARCHAR(32)     NOT NULL,
    league_id     INT             NOT NULL,
    league_name   VARCHAR(255)    NOT NULL,
    event_id      BIGINT          NOT NULL,
    home_team     VARCHAR(255)    NOT NULL,
    away_team     VARCHAR(255)    NOT NULL,

    market_type   VARCHAR(16)     NOT NULL,
    period        SMALLINT        NOT NULL,

    price_home    DECIMAL(8,4),
    price_away    DECIMAL(8,4),
    price_draw    DECIMAL(8,4),
    line          DECIMAL(6,2),
    max_bet       DECIMAL(12,2),

    recorded_at   DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    UNIQUE KEY uq_odds_snapshot (event_id, market_type, period, price_home, price_away, price_draw, line, recorded_at),
    KEY idx_odds_event   (event_id, recorded_at),
    KEY idx_odds_sport   (sport, recorded_at),
    KEY idx_odds_league  (league_id, recorded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
*/
