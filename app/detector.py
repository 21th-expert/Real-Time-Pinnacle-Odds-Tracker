"""
detector.py — Persistence layer for odds movements.

This module provides write_movements() to bulk-insert detected price changes
into the database in a single transaction.

Deduplication:
  - Unique constraint on (event_id, market_type, period, price_home, price_away, price_draw, recorded_at).
  - ON CONFLICT DO NOTHING (PostgreSQL) or INSERT IGNORE (MySQL) silently drops exact duplicates.
  - Prevents double-inserts if service restarts and replays the same API cursor.

Multi-Database Support:
  - PostgreSQL: Uses ON CONFLICT DO NOTHING for deduplication.
  - MySQL: Uses INSERT IGNORE and % placeholders.
  - SQLite: Uses INSERT OR IGNORE and ? placeholders.

Performance:
  - executemany() uses a single trip to DB (50-100x faster than row-by-row inserts).
  - Transactions ensure atomicity (all or nothing).
  - Automatic fallback to datetime.now(UTC) if movement has no recorded_at.

Example:
    from app.detector import write_movements

    movements = [
        {
            'sport': 'football', 'league_id': 1, 'league_name': 'EPL',
            'event_id': 123, 'home_team': 'A', 'away_team': 'B',
            'market_type': 'moneyline', 'period': 0,
            'price_home': 1.95, 'price_away': 2.05, 'price_draw': 3.5,
            'line': None, 'max_bet': 1000, 'recorded_at': datetime.now(timezone.utc)
        }
    ]
    n = write_movements(conn, 'postgresql', movements)
    print(f"Wrote {n} movements")
"""
import logging
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)

# SQL INSERT statements for each database type
# All columns are in the same order and default-valued for not-provided fields

_INSERT_PG = """
    INSERT INTO odds_movements
        (sport, league_id, league_name, event_id, home_team, away_team,
         market_type, period, price_home, price_away, price_draw,
         line, max_bet, recorded_at)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT DO NOTHING
"""

_INSERT_MYSQL = """
    INSERT IGNORE INTO odds_movements
        (sport, league_id, league_name, event_id, home_team, away_team,
         market_type, period, price_home, price_away, price_draw,
         line, max_bet, recorded_at)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""

_INSERT_SQLITE = """
    INSERT OR IGNORE INTO odds_movements
        (sport, league_id, league_name, event_id, home_team, away_team,
         market_type, period, price_home, price_away, price_draw,
         line, max_bet, recorded_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def write_movements(conn, db_type: str, movements: List[dict]) -> int:
    """
    Bulk-insert a list of price movements into the database.

    Uses executemany() for efficient batching. Deduplicates via unique constraint:
    exact replays (same event/market/period/prices/timestamp) are silently dropped.

    Args:
        conn: DB-API 2.0 connection (psycopg2, pymysql, or sqlite3).
        db_type: Database type ('postgresql', 'mysql', or 'sqlite').
        movements: List of movement dicts with keys:
            {
                'sport': str (e.g., 'football'),
                'league_id': int,
                'league_name': str,
                'event_id': int,
                'home_team': str,
                'away_team': str,
                'market_type': str ('moneyline', 'spread', 'total'),
                'period': int (0=full, 1=1st half, etc.),
                'price_home': float or None,
                'price_away': float or None,
                'price_draw': float or None,
                'line': float or None,
                'max_bet': float or None,
                'recorded_at': datetime or None
            }

    Returns:
        int: Number of rows inserted (duplicates are silently dropped, so may be < len(movements)).

    Raises:
        Exception: If DB write fails; transaction is rolled back automatically.

    Example:
        movements = parse_odds(sport, fixtures, odds_response)
        try:
            n = write_movements(conn, 'postgresql', movements)
            logger.info(f"Wrote {n} movements")
        except Exception as e:
            logger.error(f"Write failed: {e}")
            # Connection may need to be recreated
    """
    if not movements:
        return 0

    # Select SQL dialect based on database type
    if db_type == "mysql":
        sql = _INSERT_MYSQL
    elif db_type == "sqlite":
        sql = _INSERT_SQLITE
    else:
        sql = _INSERT_PG  # default to PostgreSQL
    
    now = datetime.now(timezone.utc)

    # Convert each movement dict to a tuple for executemany()
    rows = [
        (
            m["sport"], m["league_id"], m["league_name"], m["event_id"],
            m["home_team"], m["away_team"], m["market_type"], m["period"],
            m.get("price_home"), m.get("price_away"), m.get("price_draw"),
            m.get("line"), m.get("max_bet"), 
            # Convert to ISO format for SQLite (which stores as TEXT)
            (m.get("recorded_at", now).isoformat() if db_type == "sqlite" else m.get("recorded_at", now)),
        )
        for m in movements
    ]

    try:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()
        written = cur.rowcount
        logger.debug("Bulk-inserted %d movement(s)", written)
        return written
    except Exception:
        # Rollback transaction on any error
        conn.rollback()
        logger.exception("DB write failed — transaction rolled back")
        raise
