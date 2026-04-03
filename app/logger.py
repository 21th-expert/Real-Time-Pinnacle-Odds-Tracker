"""
logger.py — Configures the root logger for the entire service.

Call `setup_logging()` once in main.py before any other module logs.
All modules then use `logging.getLogger(__name__)` as normal.
"""
import logging
import os


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
