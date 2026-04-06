"""
logger.py — Centralized logging configuration.

This module sets up structured logging for the entire service:
  - A single root logger with configurable level (DEBUG/INFO/WARNING/ERROR).
  - Consistent timestamp format (ISO 8601 UTC).
  - All modules use logging.getLogger(__name__) to get per-module loggers.

Call setup_logging() once in main() before any other module calls logger methods.

Example usage in other modules:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Starting service")
    logger.warning("Rate limit hit")
    logger.error("Database error: %s", exc)
"""
import logging
import os


def setup_logging() -> None:
    """
    Configure the root logger with level and format from environment.

    Environment:
        LOG_LEVEL: One of DEBUG, INFO, WARNING, ERROR (default: INFO)

    Output Format:
        YYYY-MM-DDTHH:MM:SSZ LEVEL MODULE — message
        Example: 2024-01-15T10:23:45Z INFO apps.main — Started tracker
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

