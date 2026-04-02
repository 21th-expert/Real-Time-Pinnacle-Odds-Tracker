# Project Proposal — Real-Time Pinnacle Odds Tracker

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   poller.py (main)                  │
│  Thread: football          Thread: basketball       │
│  ┌──────────────────┐      ┌──────────────────┐     │
│  │ PinnacleClient   │      │ PinnacleClient   │     │
│  │ (back-off, auth) │      │ (back-off, auth) │     │
│  └────────┬─────────┘      └────────┬─────────┘     │
│           │ raw JSON                │ raw JSON       │
│  ┌────────▼─────────┐      ┌────────▼─────────┐     │
│  │   parser.py      │      │   parser.py      │     │
│  └────────┬─────────┘      └────────┬─────────┘     │
│           │ movement dicts          │                │
│  ┌────────▼─────────────────────────▼─────────┐     │
│  │              writer.py                     │     │
│  │         (bulk INSERT, dedup)               │     │
│  └────────────────────┬────────────────────── ┘     │
└───────────────────────┼─────────────────────────────┘
                        │
              ┌─────────▼──────────┐
              │  PostgreSQL/MySQL  │
              │  odds_movements    │
              └────────────────────┘
```

Each sport runs in its own thread so a slow API response for one sport never blocks the other.

---

## 2. Rate-Limit Management

### Strategy: cursor-based delta polling

The Pinnacle v3 API returns a `last` opaque integer with every response. Passing it back on the next request tells the server to return **only lines that changed** since that snapshot. This is the single most important rate-limit technique — it keeps payloads tiny and avoids redundant writes.

### Back-off policy

| Condition | Action |
|---|---|
| HTTP 429 | Sleep for `Retry-After` header value (fallback: exponential) |
| HTTP 5xx | Exponential back-off: 1 s → 2 s → 4 s … capped at 60 s |
| Network error | Same exponential back-off |
| Success | Reset attempt counter; sleep `POLL_INTERVAL` seconds |

### Configurable poll interval

`POLL_INTERVAL` defaults to 5 seconds. Pinnacle's fair-use guidance suggests no faster than 1 request/second per endpoint. With two sports × two endpoints (odds + fixtures), the service makes at most ~4 req/s at the 1 s floor — well within limits.

---

## 3. Database Design

### Single table: `odds_movements`

A single append-only table is chosen over a normalised multi-table schema for these reasons:

- **Simplicity** — no joins needed for the most common query (price history for an event).
- **Write throughput** — one INSERT path, no FK lookups.
- **Time-series friendly** — partitioning by `recorded_at` is straightforward if volume grows.

### Deduplication

A unique index on `(event_id, market_type, period, price_home, price_away, price_draw, line, recorded_at)` means the service can safely restart and replay the last cursor window without creating duplicate rows. `INSERT IGNORE` (MySQL) / `ON CONFLICT DO NOTHING` (PostgreSQL) makes this zero-cost at the application layer.

### Indexes

| Index | Purpose |
|---|---|
| `uq_odds_snapshot` | Deduplication on insert |
| `idx_odds_event` | Price history for a single event |
| `idx_odds_sport_time` | Dashboard queries filtered by sport |
| `idx_odds_league` | League-level aggregations |

### Future scaling options

- **Partitioning** by `recorded_at` (monthly) once the table exceeds ~100 M rows.
- **TimescaleDB** hypertable on top of PostgreSQL for automatic time-series compression.
- **Read replica** for analytics queries so writes are never blocked.

---

## 4. Resilience & Operations

| Concern | Solution |
|---|---|
| DB connection drop | Writer catches exceptions, closes stale connection, reconnects next cycle |
| API credential expiry | Logged as ERROR; thread keeps retrying with back-off |
| Container crash | `restart: unless-stopped` in Docker Compose |
| Log retention | Structured logs to stdout (captured by Docker) + optional file handler |
| Schema migration | Re-run `schema.sql` — all DDL uses `IF NOT EXISTS` |

---

## 5. Testing Strategy

### Unit tests (no external dependencies)

- `test_parser.py` — verifies moneyline, spread, and total parsing against a fixture payload; edge case: missing fixture metadata.
- `test_writer.py` — uses SQLite in-memory DB to verify insert, deduplication, and empty-list short-circuit.

### Integration tests (requires live credentials)

Run manually or in CI with real credentials:

```bash
PINNACLE_USERNAME=x PINNACLE_PASSWORD=x python -c "
from src.pinnacle_client import PinnacleClient, SPORT_IDS
c = PinnacleClient('x','x','https://api.ps3838.com/v3')
r = c.get_odds(SPORT_IDS['football'])
assert 'leagues' in r or 'last' in r
print('OK', r.get('last'))
"
```

### Load / soak test

Run the service for 24 hours against a staging DB and verify:
- Row count grows monotonically.
- No duplicate rows (query the unique index).
- Memory usage stays flat (no leaks in the polling loop).

---

## 6. Delivery Checklist

- [x] `src/poller.py` — main loop, threading, graceful shutdown
- [x] `src/pinnacle_client.py` — HTTP client, back-off, cursor support
- [x] `src/parser.py` — moneyline / spread / total normalisation
- [x] `src/writer.py` — bulk insert with dedup
- [x] `src/db.py` — MySQL + PostgreSQL connection factory
- [x] `src/config.py` — env-var config
- [x] `sql/schema.sql` — PostgreSQL + MySQL DDL
- [x] `Dockerfile` + `docker-compose.yml`
- [x] `.env.example`
- [x] `tests/test_parser.py` + `tests/test_writer.py`
- [x] `README.md`
- [x] `PROPOSAL.md` (this file)
