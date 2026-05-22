"""Central logging for the fund crawler process (file + stderr)."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fund_platform import settings as fp_settings

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False
_LOG_FILE: Path | None = None


def setup_crawler_logging() -> Path:
    """Configure root logging: stderr + rotating file under CRAWLER_LOG_DIR."""
    global _CONFIGURED, _LOG_FILE
    if _CONFIGURED and _LOG_FILE is not None:
        return _LOG_FILE

    log_dir = fp_settings.crawler_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "crawler.log"

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    ):
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    for name in ("apscheduler", "apscheduler.scheduler"):
        sched_logger = logging.getLogger(name)
        sched_logger.setLevel(logging.INFO)

    _CONFIGURED = True
    _LOG_FILE = log_file
    logging.getLogger(__name__).info("Crawler logging initialized file=%s", log_file)
    return log_file
