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
| `LOG_LEVEL` | | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Install & Run

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env          # fill in credentials
docker compose up -d --build
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

# Apply schema (PostgreSQL):
psql -U $DB_USER -d $DB_NAME -f sql/schema.sql

cp .env.example .env   # fill in credentials

python -m app.main
```

Stop with `Ctrl+C` — handles `SIGINT`/`SIGTERM` gracefully.

---

## Run Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Project Structure

```
odds-tracker/
│
├── app/
│   ├── main.py          # entry point — polling loop, threading, shutdown
│   ├── api_client.py    # HTTP client (back-off, cursor) + response parser
│   ├── detector.py      # bulk DB inserts with deduplication
│   ├── db.py            # PostgreSQL / MySQL connection factory
│   ├── config.py        # env-var config loader
│   └── logger.py        # logging setup
│
├── sql/
│   └── schema.sql       # table + index definitions (PG + MySQL)
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## How It Works

1. One thread per sport (football, basketball) is spawned at startup.
2. Each thread calls `/fixtures` every 60 cycles to refresh team/league names.
3. Each thread calls `/odds` with the `last` cursor — only changed lines are returned.
4. `detector.py` bulk-inserts movements in one transaction; the unique index drops exact duplicates silently.
5. On any network or DB error the thread backs off exponentially (1 → 2 → 4 … 60 s) and reconnects automatically.
