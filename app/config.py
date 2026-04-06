"""
config.py — Service configuration loader.

Loads all settings from environment variables into a Config dataclass.
Uses python-dotenv to support .env file loading.

Required Environment Variables:
    PINNACLE_USERNAME    Pinnacle API username
    PINNACLE_PASSWORD    Pinnacle API password
    DB_NAME              Database name (or SQLite file path)
    DB_USER              Database user (optional for SQLite)
    DB_PASSWORD          Database password (optional for SQLite)

Optional Environment Variables (with defaults):
    PINNACLE_BASE_URL    Pinnacle API base URL (default: https://api.ps3838.com/v3)
    DB_TYPE              'postgresql' | 'mysql' | 'sqlite' (default: postgresql)
    DB_HOST              Database hostname (default: localhost)
    DB_PORT              Database port (default: 5432)
    POLL_INTERVAL        Seconds between polls (default: 5)
    SPORTS               Comma-separated sports (default: football,basketball)
    LOG_LEVEL            DEBUG | INFO | WARNING | ERROR (default: INFO)

Example:
    from app.config import load_config
    cfg = load_config()
    print(f"Polling {cfg.sports} every {cfg.poll_interval_seconds}s")
"""
import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv


@dataclass
class Config:
    """
    Service configuration container.

    Attributes:
        api_username: Pinnacle API username (from PINNACLE_USERNAME env).
        api_password: Pinnacle API password (from PINNACLE_PASSWORD env).
        api_base_url: Pinnacle API base URL (from PINNACLE_BASE_URL env, optional).

        db_type: Database type (postgresql | mysql | sqlite).
        db_host: Database host (localhost for local development).
        db_port: Database port (5432 for PostgreSQL, 3306 for MySQL).
        db_name: Database name or SQLite file path.
        db_user: Database user (required for PostgreSQL/MySQL).
        db_password: Database password (required for PostgreSQL/MySQL).

        poll_interval_seconds: Delay between API polls per sport (float).
        sports: List of sports to track (e.g., ['football', 'basketball']).
    """
    # Pinnacle API
    api_username: str
    api_password: str
    api_base_url: str

    # Database
    db_type: str        # "postgresql" | "mysql" | "sqlite"
    db_host: str
    db_port: int
    
    db_name: str
    db_user: str
    db_password: str

    # Polling
    poll_interval_seconds: float
    sports: List[str]   # e.g. ["football", "basketball"]


def load_config() -> Config:
    """
    Load service configuration from environment variables.

    Automatically loads .env file from current directory or parent directories.
    Falls back to system environment variables if .env is not found.

    Raises:
        KeyError: If required variables (PINNACLE_USERNAME, PINNACLE_PASSWORD, etc.) are missing.

    Returns:
        Config instance ready to pass to service threads.

    Example:
        cfg = load_config()
        print(f"DB: {cfg.db_type}://{cfg.db_host}:{cfg.db_port}/{cfg.db_name}")
    """
    # Load .env file (searches current dir and parent dirs)
    load_dotenv()
    
    return Config(
        api_username=os.environ["PINNACLE_USERNAME"],
        api_password=os.environ["PINNACLE_PASSWORD"],
        api_base_url=os.getenv("PINNACLE_BASE_URL", "https://api.ps3838.com/v3"),

        db_type=os.getenv("DB_TYPE", "postgresql"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", 5432)),
        db_name=os.environ["DB_NAME"],
        db_user=os.environ["DB_USER"],
        db_password=os.environ["DB_PASSWORD"],

        poll_interval_seconds=float(os.getenv("POLL_INTERVAL", "5")),
        sports=os.getenv("SPORTS", "football,basketball").split(","),
    )
