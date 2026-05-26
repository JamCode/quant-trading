# Industry PE (CNINFO 国证) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or executing-plans.

**Goal:** Store CNINFO 国证 industry static PE history from 2023 and show on `/valuation` industry tab.

**Architecture:** `industry_pe.py` fetches via AkShare, upserts `industry_pe_daily`; cron `industry_pe_cninfo_daily_sync`; one-off `examples/backfill_industry_pe_cninfo.py`; web reads `industry_pe_queries`.

**Tech Stack:** Python 3.12, AkShare, MySQL, FastAPI/Jinja2, Chart.js

---

## Deploy checklist

- [ ] Apply `schema/mysql/014_industry_pe_daily.sql` on ECS MySQL
- [ ] Run backfill: `python examples/backfill_industry_pe_cninfo.py --start 2023-01-01`
- [ ] Restart crawler + web systemd units
- [ ] Open `/quant-funds/valuation?tab=industry`
