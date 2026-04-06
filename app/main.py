"""
main.py — Service entry point and main polling loop.

This module coordinates the entire odds tracking service:
  1. Parses configuration from environment variables.
  2. Spawns one daemon thread per configured sport (e.g., football, basketball).
  3. Each thread independently polls the Pinnacle API and writes to the database.
  4. Handles graceful shutdown (SIGINT, SIGTERM) to ensure all threads exit cleanly.

Threading Model:
  - Main Thread: Initialization, signal handling, thread lifecycle.
  - Sport Threads (1–N): Each runs run_sport() as a daemon.
    * Polls API every POLL_INTERVAL seconds.
    * Maintains independent 'odds_last' and 'fixture_last' cursors.
    * Auto-reconnects to DB on connection loss.
    * All exceptions are logged; individual errors don't crash the thread.

Polling Cycle (per sport):
  1. Ensure DB connection (reconnect if down).
  2. Every 60 cycles: Refresh fixture metadata (team/event names).
  3. Fetch odds delta (using 'last' cursor for incremental updates).
  4. Parse odds into flat movement records.
  5. Bulk-insert movements (duplicates silently dropped).
  6. Advance 'odds_last' cursor.
  7. Sleep for POLL_INTERVAL seconds.
  8. Repeat.

Graceful Shutdown:
  - Receive SIGINT (Ctrl+C) or SIGTERM (from docker-compose down, systemd stop).
  - Set stop Event to signal all sport threads to exit.
  - Join all threads (wait for them to finish current cycle).
  - Exit cleanly with final log message.

Environment:
  See config.py for all configuration variables (PINNACLE_USERNAME, DB_*, etc.).

Example Invocation:
  $ python -m app.main
  2024-01-15T10:23:45Z INFO     app.main — Started poller for football
  2024-01-15T10:23:45Z INFO     app.main — Started poller for basketball
  2024-01-15T10:23:50Z INFO     app.main — [football] Fixtures refreshed (250 events)
  2024-01-15T10:23:51Z INFO     app.main — [football] 45 movement(s) written
  ...
  # (Ctrl+C)
  2024-01-15T10:24:22Z INFO     app.main — Shutdown signal received — stopping
  2024-01-15T10:24:22Z INFO     app.main — Service stopped
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

# Refresh fixture metadata every N odds poll cycles (60 * POLL_INTERVAL seconds = 5 minutes with default 5s interval)
FIXTURE_REFRESH_EVERY = 60


def run_sport(sport: str, cfg, stop: Event) -> None:
    """
    Continuously poll a single sport until stop event is set.

    This function runs in a daemon thread and handles one sport's polling independently.

    Args:
        sport: Sport name (e.g., 'football', 'basketball').
        cfg: Config instance from load_config().
        stop: Threading.Event to signal shutdown.

    Lifecycle:
      1. Establish API client with credentials.
      2. Loop until stop.is_set().
      3. Each cycle:
         - Reconnect to DB if needed (with 10s retry delay).
         - Optionally refresh fixture metadata (every 60 cycles).
         - Fetch odds delta via 'last' cursor.
         - Parse and write movements.
         - Sleep for POLL_INTERVAL seconds.
      4. Exit cleanly (no exception raised).

    State Management:
      - odds_last: Cursor value from last odds API call.
      - fixture_last: Cursor value from last fixtures API call.
      - fixtures: Lookup dict {event_id: {'home': str, 'away': str, 'starts': str}}.
      - conn: Active DB connection (may be None if connecting).
      - cycle: Counter for fixture refresh schedule.

    Error Handling:
      - DB connect failure: Log, sleep 10s, retry.
      - Fixture fetch failure: Log, skip this cycle, continue.
      - Odds fetch failure: Log, skip this cycle, continue.
      - Write failure: Log, close connection (force reconnect), continue.
      - All exceptions are caught; thread does not crash.

    Logging:
      - [<sport>] prefix in all log messages for clarity.
      - DEBUG: No changes, poll cycles, cursor updates.
      - INFO: Fixtures refreshed, movements written.
      - WARNING: API rate limits, server errors.
      - ERROR: DB failures, unrecoverable errors.
    """
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
                stop.wait(10)  # Sleep or exit on stop signal
                continue

        # Refresh fixture metadata periodically (every 60 cycles)
        if cycle % FIXTURE_REFRESH_EVERY == 0:
            try:
                fx = client.get_fixtures(sport_id, fixture_last)
                fixture_last = fx.get("last", fixture_last)
                fixtures.update(parse_fixtures(fx))
                logger.debug("[%s] Fixtures refreshed (%d events)", sport, len(fixtures))
            except Exception:
                logger.exception("[%s] Fixture fetch failed", sport)

        # Fetch odds delta (only changed lines since last cursor)
        try:
            odds = client.get_odds(sport_id, odds_last)
            new_last = odds.get("last")

            if new_last and new_last != odds_last:
                # API returned new data
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
        stop.wait(cfg.poll_interval_seconds)  # Sleep or exit on stop signal


def main() -> None:
    """
    Main entry point: Initialize service and run polling threads.

    Steps:
      1. Call setup_logging() to configure root logger.
      2. Load configuration from environment.
      3. Register signal handlers (SIGINT, SIGTERM) for graceful shutdown.
      4. For each configured sport:
         - Validate sport is recognized.
         - Spawn a daemon thread running run_sport().
         - Log thread startup.
      5. Wait (join) all threads until they exit.
      6. Log final message and exit.

    Graceful Shutdown:
      - When SIGINT (Ctrl+C) or SIGTERM (systemd, docker-compose) is received:
        * Log "Shutdown signal received"
        * Set stop Event (all threads see this and exit their loop)
        * Join all threads (wait for them to finish current cycle)
        * Log "Service stopped" and exit

    No Manual Cleanup:
      - Database connections are closed when threads exit and conn.close() is called.
      - No explicit connection cleanup in main (relies on context managers / finally blocks).
    """
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
