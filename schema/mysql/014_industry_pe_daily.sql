-- Industry average PE from CNINFO 国证行业分类 (static PE aggregates).
USE fund_svc;

CREATE TABLE IF NOT EXISTS industry_pe_daily (
  trade_date DATE NOT NULL,
  industry_code VARCHAR(32) NOT NULL COMMENT 'CNINFO industry code',
  industry_name VARCHAR(64) NOT NULL,
  industry_level TINYINT UNSIGNED NOT NULL COMMENT '1-4',
  pe_weighted DECIMAL(16, 4) DEFAULT NULL COMMENT 'static PE weighted avg',
  pe_median DECIMAL(16, 4) DEFAULT NULL COMMENT 'static PE median',
  pe_avg DECIMAL(16, 4) DEFAULT NULL COMMENT 'static PE arithmetic avg',
  company_count INT UNSIGNED DEFAULT NULL,
  calc_company_count INT UNSIGNED DEFAULT NULL COMMENT 'included in PE calc',
  source VARCHAR(16) NOT NULL DEFAULT 'cninfo_gics',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (trade_date, industry_code),
  KEY idx_industry_pe_date_level (trade_date, industry_level),
  KEY idx_industry_pe_name (industry_name, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES ('industry_pe_cninfo_daily_sync', '行业 PE（巨潮国证）', 'cron', '', 1, 56)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind);
