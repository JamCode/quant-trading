-- Broad index PE (A-share / HK / US); industry PE out of scope for v1.
USE fund_svc;

CREATE TABLE IF NOT EXISTS index_valuation_daily (
  trade_date DATE NOT NULL,
  region VARCHAR(8) NOT NULL COMMENT 'cn|hk|us',
  index_code VARCHAR(32) NOT NULL COMMENT 'stable key, e.g. lg:000300.SH',
  index_name VARCHAR(64) NOT NULL,
  source VARCHAR(16) NOT NULL COMMENT 'legu|yfinance|shiller',
  pe_ttm DECIMAL(16, 4) DEFAULT NULL COMMENT 'trailing / rolling PE',
  pe_static DECIMAL(16, 4) DEFAULT NULL COMMENT 'static / LYR PE',
  pe_cape DECIMAL(16, 4) DEFAULT NULL COMMENT 'Shiller CAPE (US SP500 only)',
  index_close DECIMAL(16, 4) DEFAULT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (trade_date, region, index_code),
  KEY idx_index_valuation_region_date (region, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES ('index_valuation_daily_sync', '宽基指数 PE（A/港/美）', 'cron', '', 1, 55)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind);
