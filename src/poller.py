"""
poller.py — Main polling loop.

For each configured sport:
  1. Fetch fixtures (team names, league names) — refreshed every N cycles.
  2. Fetch odds using the `last` cursor so only *changed* lines come back.
  3. Parse the delta into flat movement dicts.
  4. Write movements to the database.
  5. Sleep for the configured interval before the next cycle.

The loop is intentionally simple: one thread per sport, sharing one DB connection.
If the DB connection drops it is re-established automatically.
"""
import logging
import signal
import time
from threading import Event

from config import load_config
from db import get_connection
from parser import parse_fixtures, parse_odds
from pinnacle_client import SPORT_IDS, PinnacleClient
from writer import write_movements

logger = logging.getLogger(__name__)

# Refresh fixture metadata every this many odds polls
FIXTURE_REFRESH_EVERY = 60


def run_sport(sport: str, cfg, stop_event: Event):
    """Poll one sport until stop_event is set."""
    client = PinnacleClient(cfg.api_username, cfg.api_password, cfg.api_base_url)
    sport_id = SPORT_IDS[sport.lower()]

    conn = None
    odds_last = None
    fixture_last = None
    fixtures_by_id: dict = {}
    cycle = 0

    while not stop_event.is_set():
        # --- (Re)connect to DB if needed ---
        if conn is None:
            try:
                conn = get_connection(cfg)
            except Exception:
                logger.exception("DB connect failed; retrying in 10s")
                stop_event.wait(10)
                continue

        # --- Refresh fixtures periodically ---
        if cycle % FIXTURE_REFRESH_EVERY == 0:
            try:
                fx_resp = client.get_fixtures(sport_id, fixture_last)
                fixture_last = fx_resp.get("last", fixture_last)
                fixtures_by_id.update(parse_fixtures(fx_resp))
                logger.debug("[%s] Fixtures refreshed (%d events)", sport, len(fixtures_by_id))
            except Exception:
                logger.exception("[%s] Fixture fetch failed", sport)

        # --- Fetch odds delta ---
        try:
            odds_resp = client.get_odds(sport_id, odds_last)
            new_last = odds_resp.get("last")

            if new_last and new_last != odds_last:
                movements = parse_odds(sport, fixtures_by_id, odds_resp)
                if movements:
                    try:
                        n = write_movements(conn, cfg.db_type, movements)
                        logger.info("[%s] %d movement(s) written", sport, n)
                    except Exception:
                        # Connection likely dead — drop it so it reconnects next cycle
                        logger.exception("[%s] Write error; will reconnect", sport)
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
        stop_event.wait(cfg.poll_interval_seconds)


def main():
    import threading

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    cfg = load_config()
    stop_event = Event()

    # Graceful shutdown on SIGINT / SIGTERM
    def _shutdown(signum, frame):
        logger.info("Shutdown signal received")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    threads = []
    for sport in cfg.sports:
        sport = sport.strip()
        if sport not in SPORT_IDS:
            logger.warning("Unknown sport %r — skipping", sport)
            continue
        t = threading.Thread(target=run_sport, args=(sport, cfg, stop_event), name=sport, daemon=True)
        t.start()
        threads.append(t)
        logger.info("Started poller for %s", sport)

    for t in threads:
        t.join()

    logger.info("Service stopped")


if __name__ == "__main__":
    main()
