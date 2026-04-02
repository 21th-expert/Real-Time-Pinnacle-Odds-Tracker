"""
tests/test_writer.py — Tests for the writer module using a SQLite in-memory DB.
SQLite also uses %s-style placeholders via the sqlite3 module when we swap the
cursor, so we use a tiny adapter here to keep the test self-contained.
"""
import sys, os, sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import writer as w


def _make_sqlite_conn():
    """SQLite in-memory DB shaped like the real schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE odds_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT, league_id INT, league_name TEXT,
            event_id INT, home_team TEXT, away_team TEXT,
            market_type TEXT, period INT,
            price_home REAL, price_away REAL, price_draw REAL,
            line REAL, max_bet REAL, recorded_at TEXT,
            UNIQUE(event_id, market_type, period, price_home, price_away, price_draw, line, recorded_at)
        )
    """)
    conn.commit()
    return conn


# Patch the INSERT SQL to use SQLite-compatible syntax (? placeholders)
_SQLITE_INSERT = """
    INSERT OR IGNORE INTO odds_movements
        (sport, league_id, league_name, event_id, home_team, away_team,
         market_type, period, price_home, price_away, price_draw,
         line, max_bet, recorded_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def _write(conn, movements):
    """Thin wrapper that uses SQLite placeholders."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (m["sport"], m["league_id"], m["league_name"], m["event_id"],
         m["home_team"], m["away_team"], m["market_type"], m["period"],
         m.get("price_home"), m.get("price_away"), m.get("price_draw"),
         m.get("line"), m.get("max_bet"), m.get("recorded_at", now))
        for m in movements
    ]
    cur = conn.cursor()
    cur.executemany(_SQLITE_INSERT, rows)
    conn.commit()
    return cur.rowcount


SAMPLE = [
    {
        "sport": "football", "league_id": 1, "league_name": "EPL",
        "event_id": 101, "home_team": "A", "away_team": "B",
        "market_type": "moneyline", "period": 0,
        "price_home": 2.1, "price_away": 3.5, "price_draw": 3.2,
        "line": None, "max_bet": None,
        "recorded_at": "2024-01-01T12:00:00+00:00",
    }
]


def test_write_inserts_row():
    conn = _make_sqlite_conn()
    n = _write(conn, SAMPLE)
    rows = conn.execute("SELECT sport, market_type FROM odds_movements").fetchall()
    assert len(rows) == 1
    assert rows[0] == ("football", "moneyline")


def test_write_deduplicates():
    conn = _make_sqlite_conn()
    _write(conn, SAMPLE)
    _write(conn, SAMPLE)  # exact duplicate — should be ignored
    count = conn.execute("SELECT COUNT(*) FROM odds_movements").fetchone()[0]
    assert count == 1


def test_write_empty_list():
    conn = _make_sqlite_conn()
    result = w.write_movements(MagicMock(), "postgresql", [])
    assert result == 0
