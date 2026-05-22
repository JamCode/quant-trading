"""Runtime configuration for fund web UI."""

from __future__ import annotations

import os


def listen_host() -> str:
    return os.environ.get("FUND_WEB_HOST", "127.0.0.1")


def listen_port() -> int:
    return int(os.environ.get("FUND_WEB_PORT", "8000"))


def url_prefix() -> str:
    """External URL path without trailing slash (e.g. /quant-funds for nginx subpath)."""
    return os.environ.get("FUND_URL_PREFIX", "").strip().rstrip("/")
