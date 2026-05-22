-- Major A-share indices: intraday snapshots + daily close.
USE fund_svc;

CREATE TABLE IF NOT EXISTS market_index_intraday (
  quote_time DATETIME(3) NOT NULL COMMENT '采集时刻(本地时区)',
  code VARCHAR(16) NOT NULL COMMENT '指数代码如 000001',
  name VARCHAR(64) NOT NULL DEFAULT '',
  last_price DECIMAL(16, 4) DEFAULT NULL,
  change_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨跌幅%',
  change_amt DECIMAL(16, 4) DEFAULT NULL,
  open_px DECIMAL(16, 4) DEFAULT NULL,
  high_px DECIMAL(16, 4) DEFAULT NULL,
  low_px DECIMAL(16, 4) DEFAULT NULL,
  prev_close DECIMAL(16, 4) DEFAULT NULL,
  volume BIGINT UNSIGNED DEFAULT NULL,
  amount DECIMAL(20, 2) DEFAULT NULL COMMENT '成交额',
  amplitude_pct DECIMAL(12, 4) DEFAULT NULL,
  PRIMARY KEY (quote_time, code),
  KEY idx_mi_intraday_code (code, quote_time DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS market_index_daily (
  trade_date DATE NOT NULL,
  code VARCHAR(16) NOT NULL,
  name VARCHAR(64) NOT NULL DEFAULT '',
  open_px DECIMAL(16, 4) DEFAULT NULL,
  high_px DECIMAL(16, 4) DEFAULT NULL,
  low_px DECIMAL(16, 4) DEFAULT NULL,
  close_px DECIMAL(16, 4) DEFAULT NULL,
  prev_close DECIMAL(16, 4) DEFAULT NULL,
  change_pct DECIMAL(12, 4) DEFAULT NULL,
  change_amt DECIMAL(16, 4) DEFAULT NULL,
  volume BIGINT UNSIGNED DEFAULT NULL,
  amount DECIMAL(20, 2) DEFAULT NULL,
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (trade_date, code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
