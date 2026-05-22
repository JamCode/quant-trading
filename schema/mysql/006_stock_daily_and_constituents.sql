-- A-share daily snapshot + THS industry constituent codes (join for sector cap).
USE fund_svc;

CREATE TABLE IF NOT EXISTS stock_daily (
  trade_date DATE NOT NULL,
  code VARCHAR(6) NOT NULL,
  name VARCHAR(64) NOT NULL DEFAULT '',
  price DECIMAL(14, 4) DEFAULT NULL COMMENT '最新价',
  change_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨跌幅%',
  float_market_cap DECIMAL(18, 2) DEFAULT NULL COMMENT '流通市值(亿)',
  total_market_cap DECIMAL(18, 2) DEFAULT NULL COMMENT '总市值(亿)',
  turnover_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '换手率%',
  amount DECIMAL(18, 2) DEFAULT NULL COMMENT '成交额(亿)',
  pe_dynamic DECIMAL(16, 4) DEFAULT NULL COMMENT '市盈率(动态)',
  pb DECIMAL(16, 4) DEFAULT NULL COMMENT '市净率',
  volume_ratio DECIMAL(16, 4) DEFAULT NULL COMMENT '量比',
  amplitude_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '振幅%',
  change_5m_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '5分钟涨跌%',
  speed_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨速%',
  change_60d_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '60日涨跌幅%',
  change_ytd_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '年初至今涨跌幅%',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (trade_date, code),
  KEY idx_stock_daily_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sector_industry_constituent (
  trade_date DATE NOT NULL,
  industry VARCHAR(64) NOT NULL,
  code VARCHAR(6) NOT NULL,
  PRIMARY KEY (trade_date, industry, code),
  KEY idx_sector_constituent_industry (trade_date, industry)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS stock_daily_jobs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  trade_date DATE NOT NULL,
  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  row_count INT UNSIGNED DEFAULT NULL,
  ok TINYINT(1) NOT NULL DEFAULT 0,
  error TEXT,
  PRIMARY KEY (id),
  KEY idx_stock_daily_jobs_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
