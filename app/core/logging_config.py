"""Application logging."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_dir: Path | None = None) -> None:
    """Configure console + file logging for the desktop app."""
    if logging.getLogger().handlers:
        return

    log_dir = log_dir or Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "techbench.log"

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.getLogger("techbench").info("Logging initialized at %s", log_file)
