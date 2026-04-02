# Real-Time Pinnacle Odds Tracker

Polls the PS3838 / Pinnacle v3 API for Football and Basketball line changes and writes every movement to PostgreSQL or MySQL with a UTC timestamp.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PINNACLE_USERNAME` | ✅ | — | API username |
| `PINNACLE_PASSWORD` | ✅ | — | API password |
| `PINNACLE_BASE_URL` | | `https://api.ps3838.com/v3` | API base URL |
| `DB_TYPE` | | `postgresql` | `postgresql` or `mysql` |
| `DB_HOST` | | `localhost` | Database host |
| `DB_PORT` | | `5432` | Database port |
| `DB_NAME` | ✅ | — | Database name |
| `DB_USER` | ✅ | — | Database user |
| `DB_PASSWORD` | ✅ | — | Database password |
| `POLL_INTERVAL` | | `5` | Seconds between polls per sport |
| `SPORTS` | | `football,basketball` | Comma-separated sports to track |

---

## Install & Run

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env          # fill in credentials
docker compose up -d --build  # starts DB + tracker
docker compose logs -f tracker
```

Stop:
```bash
docker compose down
```

### Option B — Local Python

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# Apply schema (PostgreSQL example):
psql -U $DB_USER -d $DB_NAME -f sql/schema.sql

cp .env.example .env   # fill in credentials
set -a && source .env && set +a   # load env vars (Linux/macOS)
# Windows: set each variable manually or use a tool like direnv

python src/poller.py
```

Stop with `Ctrl+C` — the service handles `SIGINT`/`SIGTERM` gracefully.

---

## Run Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Project Structure

```
├── src/
│   ├── poller.py          # main polling loop (entry point)
│   ├── pinnacle_client.py # HTTP client with back-off
│   ├── parser.py          # API response → flat dicts
│   ├── writer.py          # bulk DB inserts
│   ├── db.py              # connection factory
│   └── config.py          # env-var config loader
├── sql/
│   └── schema.sql         # table + index definitions
├── tests/
│   ├── test_parser.py
│   └── test_writer.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## How It Works

1. One thread is spawned per sport (football, basketball).
2. Each thread calls `/fixtures` every 60 cycles to refresh team/league names.
3. Each thread calls `/odds` with the `last` cursor — the API returns **only changed lines**, keeping bandwidth and DB writes minimal.
4. New movements are bulk-inserted in a single transaction. The unique index silently drops exact duplicates on restart.
5. On any network or DB error the thread backs off exponentially (1 → 2 → 4 … 60 s) and reconnects automatically.
