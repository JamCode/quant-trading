#!/usr/bin/env python3
"""Run the fund catalog web UI (FastAPI + scheduled AkShare sync)."""

from __future__ import annotations

import logging

import uvicorn

from quant_trading.funds import config
from quant_trading.funds.app import app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    uvicorn.run(app, host=config.listen_host(), port=config.listen_port())


if __name__ == "__main__":
    main()
