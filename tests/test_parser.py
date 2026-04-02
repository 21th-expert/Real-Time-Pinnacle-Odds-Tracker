"""
tests/test_parser.py — Unit tests for the parser module.
Run with: python -m pytest tests/
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from parser import parse_fixtures, parse_odds


FIXTURE_PAYLOAD = {
    "league": [
        {
            "id": 1,
            "events": [
                {"id": 101, "home": "Team A", "away": "Team B", "starts": "2024-01-01T15:00:00Z"}
            ],
        }
    ]
}

ODDS_PAYLOAD = {
    "last": 999,
    "leagues": [
        {
            "id": 1,
            "name": "Premier League",
            "events": [
                {
                    "id": 101,
                    "periods": [
                        {
                            "number": 0,
                            "moneyline": {"home": 2.1, "away": 3.5, "draw": 3.2},
                            "spreads": [{"hdp": -0.5, "home": 1.95, "away": 1.95, "max": 500}],
                            "totals": [{"points": 2.5, "over": 1.9, "under": 2.0, "max": 300}],
                        }
                    ],
                }
            ],
        }
    ],
}


def test_parse_fixtures():
    result = parse_fixtures(FIXTURE_PAYLOAD)
    assert 101 in result
    assert result[101]["home"] == "Team A"
    assert result[101]["away"] == "Team B"


def test_parse_odds_moneyline():
    fixtures = parse_fixtures(FIXTURE_PAYLOAD)
    movements = parse_odds("football", fixtures, ODDS_PAYLOAD)
    ml = [m for m in movements if m["market_type"] == "moneyline"]
    assert len(ml) == 1
    assert ml[0]["price_home"] == 2.1
    assert ml[0]["price_draw"] == 3.2
    assert ml[0]["sport"] == "football"
    assert ml[0]["league_name"] == "Premier League"


def test_parse_odds_spread():
    fixtures = parse_fixtures(FIXTURE_PAYLOAD)
    movements = parse_odds("football", fixtures, ODDS_PAYLOAD)
    spreads = [m for m in movements if m["market_type"] == "spread"]
    assert len(spreads) == 1
    assert spreads[0]["line"] == -0.5
    assert spreads[0]["max_bet"] == 500


def test_parse_odds_total():
    fixtures = parse_fixtures(FIXTURE_PAYLOAD)
    movements = parse_odds("football", fixtures, ODDS_PAYLOAD)
    totals = [m for m in movements if m["market_type"] == "total"]
    assert len(totals) == 1
    assert totals[0]["line"] == 2.5
    assert totals[0]["price_home"] == 1.9
    assert totals[0]["price_away"] == 2.0


def test_parse_odds_no_fixtures():
    """Parser should still work even if fixture metadata is missing."""
    movements = parse_odds("basketball", {}, ODDS_PAYLOAD)
    assert len(movements) == 3
    assert movements[0]["home_team"] == ""
