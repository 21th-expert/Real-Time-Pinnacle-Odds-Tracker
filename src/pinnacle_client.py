"""
pinnacle_client.py — Thin HTTP client for the PS3838 / Pinnacle v3 API.

Handles:
  - HTTP Basic auth
  - Exponential back-off on 429 / 5xx
  - `last` cursor so each poll only returns *changed* lines
"""
import logging
import time
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# Sport IDs in the Pinnacle API
SPORT_IDS = {
    "football": 29,
    "basketball": 4,
}

# How long to wait (seconds) on each successive retry: 1, 2, 4, 8, 16 …
_BACKOFF_BASE = 1
_BACKOFF_MAX = 60


class PinnacleClient:
    def __init__(self, username: str, password: str, base_url: str):
        self._auth = HTTPBasicAuth(username, password)
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_odds(self, sport_id: int, last: Optional[int] = None) -> dict:
        """
        Fetch odds for one sport.
        `last` is the opaque cursor returned by the previous call;
        passing it back means the API only returns lines that changed.
        """
        params = {"sportId": sport_id, "oddsFormat": "Decimal"}
        if last is not None:
            params["last"] = last
        return self._get("/odds", params)

    def get_fixtures(self, sport_id: int, last: Optional[int] = None) -> dict:
        """Fetch fixture (event) metadata — league, teams, start time."""
        params = {"sportId": sport_id}
        if last is not None:
            params["last"] = last
        return self._get("/fixtures", params)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict) -> dict:
        url = self._base + path
        attempt = 0
        while True:
            try:
                resp = self._session.get(url, params=params, timeout=15)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    # Respect Retry-After header when present
                    wait = int(resp.headers.get("Retry-After", self._backoff(attempt)))
                    logger.warning("Rate-limited. Waiting %ss", wait)
                    time.sleep(wait)

                elif resp.status_code in (500, 502, 503, 504):
                    wait = self._backoff(attempt)
                    logger.warning("Server error %s. Retrying in %ss", resp.status_code, wait)
                    time.sleep(wait)

                else:
                    resp.raise_for_status()

            except requests.RequestException as exc:
                wait = self._backoff(attempt)
                logger.error("Request failed: %s. Retrying in %ss", exc, wait)
                time.sleep(wait)

            attempt += 1

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
