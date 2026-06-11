"""Structured logging setup for the project.

Replaces ad-hoc ``print()`` with proper logging so that:
- severity levels are available for filtering
- trace IDs can be injected in the future
- logs can be forwarded to Loki / CloudWatch / etc.
"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a consistent stream handler."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
