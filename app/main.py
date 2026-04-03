"""
main.py — Service entry point.

Spawns one polling thread per configured sport. Each thread:
  1. Refreshes fixture metadata (team/league names) every 60 cycles.
  2. Fetches the odds delta via the `last` cursor.
  3. Parses the response into flat movement dicts.
  4. Bulk-inserts new movements; auto-reconnects on DB failure.

Handles SIGINT / SIGTERM for graceful shutdown.
"""
import logging
import signal
import threading
from threading import Event

from app.api_client import SPORT_IDS, PinnacleClient, parse_fixtures, parse_odds
from app.config import load_config
from app.db import get_connection
from app.detector import write_movements
from app.logger import setup_logging

logger = logging.getLogger(__name__)

FIXTURE_REFRESH_EVERY = 60  # refresh team/league names every N odds polls


def run_sport(sport: str, cfg, stop: Event) -> None:
    """Poll one sport continuously until `stop` is set."""
    client = PinnacleClient(cfg.api_username, cfg.api_password, cfg.api_base_url)
    sport_id = SPORT_IDS[sport.lower()]

    conn = None
    odds_last = None
    fixture_last = None
    fixtures: dict = {}
    cycle = 0

    while not stop.is_set():
        # (Re)connect to DB when needed
        if conn is None:
            try:
                conn = get_connection(cfg)
            except Exception:
                logger.exception("[%s] DB connect failed; retrying in 10s", sport)
                stop.wait(10)
                continue

        # Refresh fixture metadata periodically
        if cycle % FIXTURE_REFRESH_EVERY == 0:
            try:
                fx = client.get_fixtures(sport_id, fixture_last)
                fixture_last = fx.get("last", fixture_last)
                fixtures.update(parse_fixtures(fx))
                logger.debug("[%s] Fixtures refreshed (%d events)", sport, len(fixtures))
            except Exception:
                logger.exception("[%s] Fixture fetch failed", sport)

        # Fetch odds delta
        try:
            odds = client.get_odds(sport_id, odds_last)
            new_last = odds.get("last")

            if new_last and new_last != odds_last:
                movements = parse_odds(sport, fixtures, odds)
                if movements:
                    try:
                        n = write_movements(conn, cfg.db_type, movements)
                        logger.info("[%s] %d movement(s) written", sport, n)
                    except Exception:
                        logger.exception("[%s] Write error; reconnecting", sport)
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = None
                odds_last = new_last
            else:
                logger.debug("[%s] No changes this cycle", sport)

        except Exception:
            logger.exception("[%s] Odds fetch failed", sport)

        cycle += 1
        stop.wait(cfg.poll_interval_seconds)


def main() -> None:
    setup_logging()
    cfg = load_config()
    stop = Event()

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received — stopping")
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    threads = []
    for sport in cfg.sports:
        sport = sport.strip()
        if sport not in SPORT_IDS:
            logger.warning("Unknown sport %r — skipping", sport)
            continue
        t = threading.Thread(target=run_sport, args=(sport, cfg, stop), name=sport, daemon=True)
        t.start()
        threads.append(t)
        logger.info("Started poller for %s", sport)

    for t in threads:
        t.join()

    logger.info("Service stopped")


if __name__ == "__main__":
    main()
