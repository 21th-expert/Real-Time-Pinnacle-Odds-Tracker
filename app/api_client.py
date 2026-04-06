"""
api_client.py — Pinnacle / PS3838 v3 API client with intelligent retry logic.

This module provides:
  - PinnacleClient: Authenticated HTTP client with exponential backoff.
  - parse_fixtures(): Parses /fixtures response into a lookup dict.
  - parse_odds(): Parses /odds response into flat movement records.

Key Features:
  - HTTPBasicAuth for Pinnacle API authentication.
  - Cursor-based delta polling: Pass `last` parameter to get only changed odds.
  - Exponential backoff (1s to 60s) for rate limits and server errors.
  - Respects Retry-After header from API.
  - No data loss: Failed requests retry indefinitely.

Reference:
  https://www.pinnacle.com/api/sports/  (API documentation)
  Sport IDs: football=29, basketball=4
  Odds Format: decimal (e.g., 1.95, 2.10)

Example:
    client = PinnacleClient("username", "password", "https://api.ps3838.com/v3")
    fixtures = client.get_fixtures(29)  # fetch football fixtures
    odds = client.get_odds(29, last=0)  # fetch all football odds (first call)
    new_odds = client.get_odds(29, last=999)  # fetch only changes since cursor 999
"""
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# Pinnacle Sport IDs (from API documentation)
SPORT_IDS: Dict[str, int] = {
    "football": 29,
    "basketball": 4,
}

# Exponential backoff configuration
_BACKOFF_BASE = 1  # Start with 1 second
_BACKOFF_MAX = 60  # Cap at 60 seconds


# =====================================================================================
# HTTP Client
# =====================================================================================

class PinnacleClient:
    """
    Authenticated HTTP client for Pinnacle / PS3838 v3 API.

    Handles:
      - HTTPBasicAuth with username/password.
      - Exponential backoff on rate limits (429) and server errors (5xx).
      - Respects Retry-After header.
      - Automatic retry on network errors.
      - Cursor-based delta polling (only changed odds).

    Example:
        client = PinnacleClient("myuser", "mypass", "https://api.ps3838.com/v3")
        fixtures = client.get_fixtures(29)  # football
        odds = client.get_odds(29, last=0)
    """

    def __init__(self, username: str, password: str, base_url: str):
        """
        Initialize the API client.

        Args:
            username: Pinnacle API username.
            password: Pinnacle API password.
            base_url: Base URL for API (e.g., "https://api.ps3838.com/v3").
        """
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(username, password)
        self._session.headers.update({"Accept": "application/json"})

    def get_odds(self, sport_id: int, last: Optional[int] = None) -> dict:
        """
        Fetch current odds for a sport, optionally filtering by cursor.

        Args:
            sport_id: Pinnacle sport ID (29=football, 4=basketball).
            last: Optional cursor; if provided, only changed lines are returned.
                  On first call, omit or pass None to get full snapshot.
                  On subsequent calls, pass the 'last' value from previous response.

        Returns:
            dict: API response containing leagues/events/periods/markets.
                  Top-level key 'last' indicates the new cursor position.

        Example:
            # First call: get baseline
            resp = client.get_odds(29)  # OR client.get_odds(29, last=0)
            last_cursor = resp['last']
            print(f"Got {len(resp['leagues'])} leagues")

            # Subsequent calls: only deltas
            resp = client.get_odds(29, last=last_cursor)
            print(f"Changes since cursor {last_cursor}")
        """
        params: dict = {"sportId": sport_id, "oddsFormat": "Decimal"}
        if last is not None:
            params["last"] = last
        return self._get("/odds", params)

    def get_fixtures(self, sport_id: int, last: Optional[int] = None) -> dict:
        """
        Fetch fixture metadata (team names, league names, start times).

        Args:
            sport_id: Pinnacle sport ID (29=football, 4=basketball).
            last: Optional cursor; if provided, only changed fixtures are returned.

        Returns:
            dict: API response containing leagues with events and team metadata.
                  Top-level key 'last' indicates cursor position for next call.

        Example:
            resp = client.get_fixtures(29)  # football fixtures
            for league in resp['league']:
                for event in league['events']:
                    print(f"{event['home']} vs {event['away']}")
        """
        params: dict = {"sportId": sport_id}
        if last is not None:
            params["last"] = last
        return self._get("/fixtures", params)

    def _get(self, path: str, params: dict) -> dict:
        """
        Perform authenticated GET request with exponential backoff retry logic.

        Handles:
          - 200 OK: Return parsed JSON.
          - 429 Rate Limit: Wait (respects Retry-After header), retry.
          - 5xx Server Error: Wait exponentially, retry.
          - Network errors: Wait exponentially, retry.

        Args:
            path: API path (e.g., "/odds", "/fixtures").
            params: Query parameters dict.

        Returns:
            dict: Parsed JSON response.

        Raises:
            requests.HTTPError: Only raised for unexpected HTTP status codes.
            requests.RequestException: Only raised for unrecoverable network errors.
        """
        url = self._base + path
        attempt = 0
        while True:
            try:
                resp = self._session.get(url, params=params, timeout=15)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    # Rate limited by API
                    wait = int(resp.headers.get("Retry-After", self._backoff(attempt)))
                    logger.warning(
                        "Rate-limited (429) on %s — waiting %ds before retry",
                        path, wait
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue

                if resp.status_code in (500, 502, 503, 504):
                    # Server error (temporary)
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Server error %s on %s — waiting %ds before retry",
                        resp.status_code, path, wait
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue

                # Unexpected status code
                resp.raise_for_status()

            except requests.RequestException as exc:
                # Network error, timeout, connection error, etc.
                wait = self._backoff(attempt)
                logger.error(
                    "Request error on %s: %s — waiting %ds before retry",
                    path, exc, wait
                )
                time.sleep(wait)
                attempt += 1
                # Continue to next retry

    @staticmethod
    def _backoff(attempt: int) -> float:
        """
        Calculate exponential backoff delay.

        Formula: min(1 * 2^attempt, 60)
          Attempt 0: 1s
          Attempt 1: 2s
          Attempt 2: 4s
          Attempt 3: 8s
          ...
          Attempt 6+: 60s (capped)

        Args:
            attempt: Zero-indexed retry attempt number.

        Returns:
            float: Seconds to wait before next retry.
        """
        return min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)


# =====================================================================================
# Response Parsers
# =====================================================================================

def parse_fixtures(payload: dict) -> Dict[int, dict]:
    """
    Parse /fixtures response into a lookup dictionary.

    Transforms the nested API response into a simple {event_id: metadata} dict
    for quick lookups while processing odds.

    Args:
        payload: Full response dict from client.get_fixtures().

    Returns:
        dict: Keys are event_id (int), values are dicts with:
            - 'home': Home team name (str)
            - 'away': Away team name (str)
            - 'starts': Event start time (str, ISO 8601)

    Example:
        payload = client.get_fixtures(29)
        fixtures = parse_fixtures(payload)
        # fixtures[12345] = {'home': 'Team A', 'away': 'Team B', 'starts': '2024-01-15T19:00:00Z'}
    """
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
    Flatten /odds response into a list of standardized movement dicts.

    Transforms nested API structure (leagues > events > periods > markets) into
    a flat list where each element represents one observed price point.

    Extracts:
      - Moneyline (home/away/draw odds)
      - Spreads (home/away odds with hdp line)
      - Totals (over/under odds with points)

    Args:
        sport: Sport name (e.g., "football" or "basketball").
        fixtures: Lookup dict from parse_fixtures() for team names.
        payload: Full response dict from client.get_odds().

    Returns:
        list: Each element is a dict suitable for write_movements():
            {
                'sport': str,
                'league_id': int,
                'league_name': str,
                'event_id': int,
                'home_team': str,
                'away_team': str,
                'market_type': 'moneyline' | 'spread' | 'total',
                'period': int,
                'price_home': float or None,
                'price_away': float or None,
                'price_draw': float or None,
                'line': float or None,
                'max_bet': float or None,
                'recorded_at': datetime,
            }

    Example:
        odds_payload = client.get_odds(29)
        fixtures = {123: {'home': 'A', 'away': 'B', 'starts': '2024-01-15T19:00:00Z'}}
        movements = parse_odds('football', fixtures, odds_payload)
        print(f"Parsed {len(movements)} price movements")
        # First movement might be:
        # {'sport': 'football', 'league_id': 1, 'market_type': 'moneyline', 'price_home': 1.95, ...}
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

                # Moneyline: home, away, draw odds (draw only in soccer)
                ml = period.get("moneyline")
                if ml:
                    movements.append(_movement(
                        sport, league_id, league_name, event_id, home, away,
                        "moneyline", pnum, now,
                        price_home=ml.get("home"),
                        price_away=ml.get("away"),
                        price_draw=ml.get("draw"),
                    ))

                # Spreads: multiple per period (different -/+ lines)
                for spread in period.get("spreads", []):
                    movements.append(_movement(
                        sport, league_id, league_name, event_id, home, away,
                        "spread", pnum, now,
                        price_home=spread.get("home"),
                        price_away=spread.get("away"),
                        line=spread.get("hdp"),
                        max_bet=spread.get("max"),
                    ))

                # Totals: multiple per period (different point values)
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
    """
    Construct a movement dict from parsed API data.

    Helper function to normalize field names and structure.

    Args:
        sport: Sport name (str).
        league_id: League ID (int).
        league_name: League name (str).
        event_id: Event ID (int).
        home: Home team name (str).
        away: Away team name (str).
        market_type: 'moneyline', 'spread', or 'total'.
        period: Period number (int).
        recorded_at: datetime when observed.
        **kw: Arbitrary keyword args:
            - price_home, price_away, price_draw: Decimal odds or None.
            - line: Spread hdp or total points, or None.
            - max_bet: Maximum stake, or None.

    Returns:
        dict: Normalized movement record ready for DB insertion.
    """
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
