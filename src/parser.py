"""
parser.py — Converts raw Pinnacle API responses into flat movement dicts.

Supports:
  - Moneyline (1X2 / home-away)
  - Spread (handicap)
  - Total (over/under)
"""
from datetime import datetime, timezone
from typing import List


def parse_odds(sport: str, fixtures_by_id: dict, odds_payload: dict) -> List[dict]:
    """
    Walk the nested odds payload and return a flat list of movement dicts,
    one per price point per market per period per event.
    """
    movements = []
    now = datetime.now(timezone.utc)

    for league in odds_payload.get("leagues", []):
        league_id = league["id"]
        league_name = league.get("name", "")

        for event in league.get("events", []):
            event_id = event["id"]
            fixture = fixtures_by_id.get(event_id, {})
            home = fixture.get("home", "")
            away = fixture.get("away", "")

            for period in event.get("periods", []):
                period_num = period["number"]

                # --- Moneyline ---
                ml = period.get("moneyline")
                if ml:
                    movements.append(_row(
                        sport, league_id, league_name, event_id, home, away,
                        "moneyline", period_num,
                        price_home=ml.get("home"),
                        price_away=ml.get("away"),
                        price_draw=ml.get("draw"),
                        recorded_at=now,
                    ))

                # --- Spreads ---
                for spread in period.get("spreads", []):
                    movements.append(_row(
                        sport, league_id, league_name, event_id, home, away,
                        "spread", period_num,
                        price_home=spread.get("home"),
                        price_away=spread.get("away"),
                        line=spread.get("hdp"),
                        max_bet=spread.get("max"),
                        recorded_at=now,
                    ))

                # --- Totals ---
                for total in period.get("totals", []):
                    movements.append(_row(
                        sport, league_id, league_name, event_id, home, away,
                        "total", period_num,
                        price_home=total.get("over"),
                        price_away=total.get("under"),
                        line=total.get("points"),
                        max_bet=total.get("max"),
                        recorded_at=now,
                    ))

    return movements


def parse_fixtures(fixtures_payload: dict) -> dict:
    """Return {event_id: {home, away, starts}} from a fixtures response."""
    result = {}
    for league in fixtures_payload.get("league", []):
        for event in league.get("events", []):
            result[event["id"]] = {
                "home": event.get("home", ""),
                "away": event.get("away", ""),
                "starts": event.get("starts", ""),
            }
    return result


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _row(sport, league_id, league_name, event_id, home, away,
         market_type, period, recorded_at, **kwargs) -> dict:
    return {
        "sport": sport,
        "league_id": league_id,
        "league_name": league_name,
        "event_id": event_id,
        "home_team": home,
        "away_team": away,
        "market_type": market_type,
        "period": period,
        "price_home": kwargs.get("price_home"),
        "price_away": kwargs.get("price_away"),
        "price_draw": kwargs.get("price_draw"),
        "line": kwargs.get("line"),
        "max_bet": kwargs.get("max_bet"),
        "recorded_at": recorded_at,
    }
