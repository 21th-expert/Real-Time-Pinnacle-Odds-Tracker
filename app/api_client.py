"""
api_client.py — Pinnacle / PS3838 v3 HTTP client and response parser.

Responsibilities:
  - Authenticated requests with exponential back-off (429 / 5xx / network errors).
  - `last` cursor support so each poll returns only *changed* lines.
  - Parsing raw API JSON into flat movement dicts ready for the DB.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# Pinnacle sport IDs
SPORT_IDS: Dict[str, int] = {
    "football": 29,
    "basketball": 4,
}

_BACKOFF_BASE = 1
_BACKOFF_MAX = 60


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class PinnacleClient:
    def __init__(self, username: str, password: str, base_url: str):
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(username, password)
        self._session.headers.update({"Accept": "application/json"})

    def get_odds(self, sport_id: int, last: Optional[int] = None) -> dict:
        """Fetch odds delta. Pass `last` to receive only changed lines."""
        params: dict = {"sportId": sport_id, "oddsFormat": "Decimal"}
        if last is not None:
            params["last"] = last
        return self._get("/odds", params)

    def get_fixtures(self, sport_id: int, last: Optional[int] = None) -> dict:
        """Fetch fixture metadata (teams, league, start time)."""
        params: dict = {"sportId": sport_id}
        if last is not None:
            params["last"] = last
        return self._get("/fixtures", params)

    def _get(self, path: str, params: dict) -> dict:
        url = self._base + path
        attempt = 0
        while True:
            try:
                resp = self._session.get(url, params=params, timeout=15)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", self._backoff(attempt)))
                    logger.warning("Rate-limited — waiting %ss", wait)
                    time.sleep(wait)

                elif resp.status_code in (500, 502, 503, 504):
                    wait = self._backoff(attempt)
                    logger.warning("Server error %s — retrying in %ss", resp.status_code, wait)
                    time.sleep(wait)

                else:
                    resp.raise_for_status()

            except requests.RequestException as exc:
                wait = self._backoff(attempt)
                logger.error("Request error: %s — retrying in %ss", exc, wait)
                time.sleep(wait)

            attempt += 1

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def parse_fixtures(payload: dict) -> Dict[int, dict]:
    """Return {event_id: {home, away, starts}} from a /fixtures response."""
    result: Dict[int, dict] = {}
    for league in payload.get("league", []):
        for event in league.get("events", []):
            result[event["id"]] = {
                "home": event.get("home", ""),
                "away": event.get("away", ""),
                "starts": event.get("starts", ""),
            }
    return result


def parse_odds(sport: str, fixtures: Dict[int, dict], payload: dict) -> List[dict]:
    """
    Flatten a /odds response into a list of movement dicts.
    Covers moneyline, spread, and total markets for all periods.
    """
    movements: List[dict] = []
    now = datetime.now(timezone.utc)

    for league in payload.get("leagues", []):
        league_id = league["id"]
        league_name = league.get("name", "")

        for event in league.get("events", []):
            event_id = event["id"]
            fx = fixtures.get(event_id, {})
            home, away = fx.get("home", ""), fx.get("away", "")

            for period in event.get("periods", []):
                pnum = period["number"]

                ml = period.get("moneyline")
                if ml:
                    movements.append(_movement(
                        sport, league_id, league_name, event_id, home, away,
                        "moneyline", pnum, now,
                        price_home=ml.get("home"),
                        price_away=ml.get("away"),
                        price_draw=ml.get("draw"),
                    ))

                for spread in period.get("spreads", []):
                    movements.append(_movement(
                        sport, league_id, league_name, event_id, home, away,
                        "spread", pnum, now,
                        price_home=spread.get("home"),
                        price_away=spread.get("away"),
                        line=spread.get("hdp"),
                        max_bet=spread.get("max"),
                    ))

                for total in period.get("totals", []):
                    movements.append(_movement(
                        sport, league_id, league_name, event_id, home, away,
                        "total", pnum, now,
                        price_home=total.get("over"),
                        price_away=total.get("under"),
                        line=total.get("points"),
                        max_bet=total.get("max"),
                    ))

    return movements


def _movement(sport, league_id, league_name, event_id, home, away,
              market_type, period, recorded_at, **kw) -> dict:
    return {
        "sport": sport,
        "league_id": league_id,
        "league_name": league_name,
        "event_id": event_id,
        "home_team": home,
        "away_team": away,
        "market_type": market_type,
        "period": period,
        "price_home": kw.get("price_home"),
        "price_away": kw.get("price_away"),
        "price_draw": kw.get("price_draw"),
        "line": kw.get("line"),
        "max_bet": kw.get("max_bet"),
        "recorded_at": recorded_at,
    }
