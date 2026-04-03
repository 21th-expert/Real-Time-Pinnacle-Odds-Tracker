"""
config.py — Loads all service settings from environment variables.
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # Pinnacle API
    api_username: str
    api_password: str
    api_base_url: str

    # Database
    db_type: str        # "postgresql" | "mysql"
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    # Polling
    poll_interval_seconds: float
    sports: List[str]   # e.g. ["football", "basketball"]


def load_config() -> Config:
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
