"""Compatibility shim — lazy detail cache lives in ``fund_platform.detail``."""

from fund_platform.detail import (  # noqa: F401
    ensure_fresh_detail,
    fetch_detail_bundle,
)
