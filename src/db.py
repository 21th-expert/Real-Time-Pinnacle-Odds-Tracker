"""
db.py — Database connection factory.

Returns a DB-API 2.0 connection for either MySQL (PyMySQL) or PostgreSQL (psycopg2).
Both drivers share the same %s placeholder style so the writer stays driver-agnostic.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_connection(cfg) -> Any:
    """Return a live DB-API connection based on cfg.db_type."""
    if cfg.db_type == "mysql":
        import pymysql
        conn = pymysql.connect(
            host=cfg.db_host,
            port=cfg.db_port,
            database=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_password,
            charset="utf8mb4",
            autocommit=False,
        )
        logger.info("Connected to MySQL at %s:%s/%s", cfg.db_host, cfg.db_port, cfg.db_name)
        return conn

    elif cfg.db_type == "postgresql":
        import psycopg2
        conn = psycopg2.connect(
            host=cfg.db_host,
            port=cfg.db_port,
            dbname=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_password,
        )
        conn.autocommit = False
        logger.info("Connected to PostgreSQL at %s:%s/%s", cfg.db_host, cfg.db_port, cfg.db_name)
        return conn

    else:
        raise ValueError(f"Unsupported DB_TYPE: {cfg.db_type!r}. Use 'mysql' or 'postgresql'.")
