#!/usr/bin/env python3
"""Run the daily fund crawler (writes MySQL). Requires DATABASE_URL + pip install -e '.[crawler]'"""

from __future__ import annotations

from fund_platform.crawler_cli import main

if __name__ == "__main__":
    main()
