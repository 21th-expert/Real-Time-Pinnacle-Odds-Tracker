"""
detector.py — Persists detected odds movements to the database.

`write_movements` receives a list of normalised movement dicts and
bulk-inserts them in a single transaction. Exact duplicates are silently
dropped via the unique index (ON CONFLICT DO NOTHING / INSERT IGNORE).
"""
import logging
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)

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


def write_movements(conn, db_type: str, movements: List[dict]) -> int:
    """Bulk-insert movements. Returns the number of rows written."""
    if not movements:
        return 0

    sql = _INSERT_MYSQL if db_type == "mysql" else _INSERT_PG
    now = datetime.now(timezone.utc)

    rows = [
        (
            m["sport"], m["league_id"], m["league_name"], m["event_id"],
            m["home_team"], m["away_team"], m["market_type"], m["period"],
            m.get("price_home"), m.get("price_away"), m.get("price_draw"),
            m.get("line"), m.get("max_bet"), m.get("recorded_at", now),
        )
        for m in movements
    ]

    try:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        conn.commit()
        written = cur.rowcount
        logger.debug("Wrote %d movement(s)", written)
        return written
    except Exception:
        conn.rollback()
        logger.exception("DB write failed — rolled back")
        raise
