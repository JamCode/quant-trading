-- US equities: EOD spot cross-section + static identity.
USE fund_svc;

CREATE TABLE IF NOT EXISTS us_stock_daily (
  trade_date DATE NOT NULL COMMENT '美东交易日',
  code VARCHAR(16) NOT NULL COMMENT 'Ticker e.g. AAPL',
  name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '名称(多为中文)',
  price DECIMAL(14, 4) DEFAULT NULL COMMENT '收盘价/最新价 USD',
  change_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨跌幅%',
  change_amt DECIMAL(14, 4) DEFAULT NULL COMMENT '涨跌额 USD',
  open_px DECIMAL(14, 4) DEFAULT NULL,
  high_px DECIMAL(14, 4) DEFAULT NULL,
  low_px DECIMAL(14, 4) DEFAULT NULL,
  prev_close DECIMAL(14, 4) DEFAULT NULL,
  volume BIGINT DEFAULT NULL COMMENT '成交量',
  amount DECIMAL(18, 2) DEFAULT NULL COMMENT '成交额(亿美元)',
  total_market_cap DECIMAL(18, 2) DEFAULT NULL COMMENT '总市值(亿美元)',
  turnover_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '换手率%',
  pe_dynamic DECIMAL(16, 4) DEFAULT NULL COMMENT '市盈率',
  amplitude_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '振幅%',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (trade_date, code),
  KEY idx_us_stock_daily_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS us_stock_basic (
  code VARCHAR(16) NOT NULL COMMENT 'Ticker',
  name VARCHAR(128) NOT NULL DEFAULT '',
  name_en VARCHAR(256) DEFAULT NULL,
  em_symbol VARCHAR(24) DEFAULT NULL COMMENT '东财代码 105.MSFT',
  market VARCHAR(32) DEFAULT NULL COMMENT 'NYSE/NASDAQ/AMEX等',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (code),
  KEY idx_us_stock_basic_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS us_stock_daily_jobs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  trade_date DATE NOT NULL,
  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  row_count INT UNSIGNED DEFAULT NULL,
  ok TINYINT(1) NOT NULL DEFAULT 0,
  error TEXT,
  PRIMARY KEY (id),
  KEY idx_us_stock_daily_jobs_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES
  ('us_stock_daily_sync', '美股现货日线', 'cron', '', 1, 22)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind);
