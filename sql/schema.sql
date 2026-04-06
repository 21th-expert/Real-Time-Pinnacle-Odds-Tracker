-- =====================================================================================
-- schema.sql — Pinnacle Odds Tracker Database Schema
--
-- This schema is compatible with:
--   ✓ PostgreSQL 13+  (primary recommendation)
--   ✓ MySQL 8+        (production-ready)
--   ✓ SQLite 3.31+    (development/small scale)
--
-- Design Goals:
--   1. Immutability: Each row represents an observed snapshot (never updated).
--   2. Deduplication: Unique constraint prevents replayed inserts on service restart.
--   3. Query Performance: Strategic indexes for common access patterns.
--   4. Multi-Database Support: Works across PostgreSQL, MySQL, and SQLite.
--
-- Installation:
--   PostgreSQL:  psql -U <user> -d <db> -f schema.sql
--   MySQL:       mysql -u <user> -p <db> < schema.sql
--   SQLite:      sqlite3 <db> < schema.sql
-- =====================================================================================

-- =====================================================================================
-- Table: odds_movements
--
-- Stores every observed price change for sports markets.
-- One row = one observation of a price point at a specific moment in time.
--
-- Rationale for NOT having per-market tables:
--   - Moneyline, spread, total are all the same "observation" of market state.
--   - Single table enables easy cross-market historical queries.
--   - Index strategy can optimize for common queries.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS odds_movements (
    -- Primary key and metadata
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    -- Sport identification
    sport         VARCHAR(32)     NOT NULL,
    
    -- League & event identification
    league_id     INT             NOT NULL,
    league_name   VARCHAR(255)    NOT NULL,
    event_id      BIGINT          NOT NULL,
    home_team     VARCHAR(255)    NOT NULL,
    away_team     VARCHAR(255)    NOT NULL,

    -- Market information
    market_type   VARCHAR(16)     NOT NULL,    -- 'moneyline', 'spread', 'total'
    period        SMALLINT        NOT NULL,    -- 0=full game, 1=1st half, 2=2nd half, etc.

    -- Odds (decimal format, e.g., 1.95 = 95% implied probability)
    price_home    NUMERIC(8,4),                -- Home team or Over bet
    price_away    NUMERIC(8,4),                -- Away team or Under bet
    price_draw    NUMERIC(8,4),                -- Draw (moneyline only, NULL for spread/total)

    -- Market parameters
    line          NUMERIC(6,2),                -- Spread hdp (e.g., -0.5) or total points (e.g., 225.5)
    max_bet       NUMERIC(12,2),               -- Maximum stake allowed for this market

    -- Observation timestamp (UTC)
    -- This timestamp represents when the odds were observed/captured.
    -- NOT the time the service processed it, but the actual market moment.
    recorded_at   TIMESTAMPTZ     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================================
-- Index Strategies
-- =====================================================================================

-- DEDUPLICATION INDEX
-- Prevents exact duplicates when service restarts and replays the same cursor.
-- If an identical snapshot is inserted again, ON CONFLICT DO NOTHING silently drops it.
-- Unique constraint is SPARSE (NULL values don't violate uniqueness in PostgreSQL).
CREATE UNIQUE INDEX IF NOT EXISTS uq_odds_snapshot
    ON odds_movements (event_id, market_type, period, price_home, price_away, price_draw, recorded_at);

-- EVENT HISTORY INDEX
-- Optimizes queries like: "Show me all movements for event X"
-- Common for: reverting to a specific moment in time, analyzing price evolution.
CREATE INDEX IF NOT EXISTS idx_odds_event
    ON odds_movements (event_id, recorded_at DESC);

-- SPORT + TIME INDEX
-- Optimizes queries like: "All football movements in the last hour"
-- Common for: dashboards, exports, real-time feeds.
CREATE INDEX IF NOT EXISTS idx_odds_sport_time
    ON odds_movements (sport, recorded_at DESC);

-- LEAGUE INDEX
-- Optimizes queries like: "All movements in league 1"
-- Common for: league-specific analytics, league-wide trend analysis.
CREATE INDEX IF NOT EXISTS idx_odds_league
    ON odds_movements (league_id, recorded_at DESC);

-- =====================================================================================
-- POSTGRESQL-SPECIFIC FEATURES (OPTIONAL)
-- =====================================================================================

-- Partitioning by month (PostgreSQL 11+, optional for very large tables)
-- Uncomment if you expect > 100M rows/year
/*
CREATE TABLE IF NOT EXISTS odds_movements_2024_01 PARTITION OF odds_movements
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE IF NOT EXISTS odds_movements_2024_02 PARTITION OF odds_movements
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- ... create for each month ...
*/

-- =====================================================================================
-- MAINTENANCE QUERIES (PostgreSQL)
-- =====================================================================================

-- Analyze table for query planner (run periodically)
-- ANALYZE odds_movements;

-- Vacuum and reindex (run during low-traffic periods)
-- VACUUM ANALYZE odds_movements;
-- REINDEX TABLE odds_movements;

-- =====================================================================================
-- SAMPLE QUERIES
-- =====================================================================================

-- Total records
-- SELECT COUNT(*) FROM odds_movements;

-- Records in last hour
-- SELECT COUNT(*) FROM odds_movements WHERE recorded_at > NOW() - INTERVAL '1 hour';

-- By sport in last hour
-- SELECT sport, COUNT(*) FROM odds_movements
--   WHERE recorded_at > NOW() - INTERVAL '1 hour'
--   GROUP BY sport ORDER BY COUNT(*) DESC;

-- Price history for specific event
-- SELECT market_type, period, price_home, price_away, recorded_at
--   FROM odds_movements
--   WHERE event_id = 123456 AND market_type = 'moneyline'
--   ORDER BY recorded_at DESC LIMIT 100;

-- Price movement (delta) over time
-- SELECT 
--   recorded_at,
--   price_home,
--   LAG(price_home) OVER (ORDER BY recorded_at) as prev_price,
--   price_home - LAG(price_home) OVER (ORDER BY recorded_at) as delta
-- FROM odds_movements
-- WHERE event_id = 123456 AND market_type = 'moneyline'
-- ORDER BY recorded_at;

-- =====================================================================================
-- ARCHIVAL STRATEGY (Optional)
-- =====================================================================================

-- If you only need recent data, archive/delete old records monthly.
-- Create archive table first:
-- CREATE TABLE odds_movements_archive AS SELECT * FROM odds_movements WHERE 1=0;

-- Then truncate old data:
-- DELETE FROM odds_movements WHERE recorded_at < NOW() - INTERVAL '60 days';
-- VACUUM ANALYZE odds_movements;

-- =====================================================================================

