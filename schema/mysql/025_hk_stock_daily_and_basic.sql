-- HK equities: EOD spot cross-section + static security profile fields.
USE fund_svc;

CREATE TABLE IF NOT EXISTS hk_stock_daily (
  trade_date DATE NOT NULL,
  code VARCHAR(5) NOT NULL,
  name VARCHAR(128) NOT NULL DEFAULT '',
  price DECIMAL(14, 4) DEFAULT NULL COMMENT '收盘价/最新价',
  change_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨跌幅%',
  change_amt DECIMAL(14, 4) DEFAULT NULL COMMENT '涨跌额',
  open_px DECIMAL(14, 4) DEFAULT NULL,
  high_px DECIMAL(14, 4) DEFAULT NULL,
  low_px DECIMAL(14, 4) DEFAULT NULL,
  prev_close DECIMAL(14, 4) DEFAULT NULL,
  volume BIGINT DEFAULT NULL COMMENT '成交量',
  amount DECIMAL(18, 2) DEFAULT NULL COMMENT '成交额(亿港币)',
  turnover_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '换手率%',
  pe_dynamic DECIMAL(16, 4) DEFAULT NULL COMMENT '市盈率(动态)',
  pb DECIMAL(16, 4) DEFAULT NULL COMMENT '市净率',
  amplitude_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '振幅%',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (trade_date, code),
  KEY idx_hk_stock_daily_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hk_stock_basic (
  code VARCHAR(5) NOT NULL,
  name VARCHAR(128) NOT NULL DEFAULT '',
  name_en VARCHAR(256) DEFAULT NULL,
  security_type VARCHAR(64) DEFAULT NULL COMMENT '证券/交易类型',
  board VARCHAR(64) DEFAULT NULL COMMENT '板块',
  exchange VARCHAR(32) DEFAULT NULL,
  listing_date DATE DEFAULT NULL,
  issue_price DECIMAL(14, 4) DEFAULT NULL COMMENT '发行价',
  lot_size INT DEFAULT NULL COMMENT '每手股数',
  par_value DECIMAL(14, 4) DEFAULT NULL COMMENT '每股面值',
  isin VARCHAR(32) DEFAULT NULL,
  hk_connect_sh TINYINT(1) DEFAULT NULL COMMENT '沪港通标的',
  hk_connect_sz TINYINT(1) DEFAULT NULL COMMENT '深港通标的',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (code),
  KEY idx_hk_stock_basic_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hk_stock_daily_jobs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  trade_date DATE NOT NULL,
  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  row_count INT UNSIGNED DEFAULT NULL,
  ok TINYINT(1) NOT NULL DEFAULT 0,
  error TEXT,
  PRIMARY KEY (id),
  KEY idx_hk_stock_daily_jobs_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES
  ('hk_stock_daily_sync', '港股现货日线', 'cron', '', 1, 21)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind);
