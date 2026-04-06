"""
db.py — Database connection factory.

Provides get_connection() to obtain a DB-API 2.0 connection based on configuration.
Supports PostgreSQL (psycopg2), MySQL (PyMySQL), and SQLite (sqlite3).

Design:
  - Single factory function for simplicity.
  - Returns connection object ready to use (autocommit=False for transactions).
  - All drivers use %s placeholders (or ? for SQLite), hidden by detector.py.
  - SQLite automatically creates tables/schema on first connection.

Example:
    from app.config import load_config
    from app.db import get_connection

    cfg = load_config()
    conn = get_connection(cfg)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM odds_movements")
    count = cur.fetchone()[0]
    conn.close()
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_connection(cfg) -> Any:
    """
    Factory function to create a database connection.

    Selects driver based on cfg.db_type and returns a live DB-API 2.0 connection
    ready for cursor operations and transactions.

    SQLite connections automatically create the schema tables if missing.
    PostgreSQL and MySQL assume pre-initialized schema (or use docker-entrypoint).

    Args:
        cfg: Config instance with db_type, db_host, db_port, db_name, db_user, db_password.

    Returns:
        DB-API 2.0 connection object (psycopg2, pymysql, or sqlite3).
        All support cursor(), fetchone(), fetchall(), commit(), rollback(), close().

    Raises:
        ValueError: If db_type is not recognized.
        psycopg2.DatabaseError / pymysql.DatabaseError / sqlite3.DatabaseError:
            If connection/authentication fails.

    Example:
        conn = get_connection(cfg)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM odds_movements")
            count = cur.fetchone()[0]
            print(f"Total movements: {count}")
        finally:
            conn.close()
    """
    if cfg.db_type == "mysql":
        import pymysql
        conn = pymysql.connect(
            host=cfg.db_host,
            port=cfg.db_port,
            database=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_password,
            charset="utf8mb4",
            autocommit=False,
        )
        logger.info("Connected to MySQL at %s:%s/%s", cfg.db_host, cfg.db_port, cfg.db_name)
        return conn

    elif cfg.db_type == "postgresql":
        import psycopg2
        conn = psycopg2.connect(
            host=cfg.db_host,
            port=cfg.db_port,
            dbname=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_password,
        )
        conn.autocommit = False
        logger.info("Connected to PostgreSQL at %s:%s/%s", cfg.db_host, cfg.db_port, cfg.db_name)
        return conn

    elif cfg.db_type == "sqlite":
        import sqlite3
        conn = sqlite3.connect(cfg.db_name)
        conn.execute("PRAGMA foreign_keys = ON")
        # Create table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS odds_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sport TEXT NOT NULL,
                league_id INTEGER NOT NULL,
                league_name TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                market_type TEXT NOT NULL,
                period INTEGER NOT NULL,
                price_home REAL,
                price_away REAL,
                price_draw REAL,
                line REAL,
                max_bet REAL,
                recorded_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_odds_snapshot
            ON odds_movements (event_id, market_type, period, price_home, price_away, price_draw, recorded_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_odds_event
            ON odds_movements (event_id, recorded_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_odds_sport_time
            ON odds_movements (sport, recorded_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_odds_league
            ON odds_movements (league_id, recorded_at DESC)
        """)
        conn.commit()
        logger.info("Connected to SQLite database: %s", cfg.db_name)
        return conn

    raise ValueError(f"Unsupported DB_TYPE: {cfg.db_type!r}. Use 'postgresql', 'mysql', or 'sqlite'.")
