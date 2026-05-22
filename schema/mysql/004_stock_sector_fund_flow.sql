-- A-share industry sector fund flow (AkShare stock_fund_flow_industry), daily snapshot.
USE fund_svc;

CREATE TABLE IF NOT EXISTS sector_flow_jobs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  trade_date DATE NOT NULL,
  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  period VARCHAR(16) NOT NULL,
  row_count INT UNSIGNED DEFAULT NULL,
  ok TINYINT(1) NOT NULL DEFAULT 0,
  error TEXT,
  PRIMARY KEY (id),
  KEY idx_sector_flow_jobs_date (trade_date, period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sector_fund_flow (
  trade_date DATE NOT NULL COMMENT '抓取交易日(按服务器本地日)',
  period VARCHAR(16) NOT NULL COMMENT '即时|3日排行|5日排行|10日排行|20日排行',
  industry VARCHAR(64) NOT NULL COMMENT '行业名称',
  industry_index VARCHAR(32) NOT NULL DEFAULT '',
  change_pct VARCHAR(32) NOT NULL DEFAULT '' COMMENT '行业或阶段涨跌幅',
  inflow_amt DECIMAL(18, 2) DEFAULT NULL COMMENT '流入资金(亿)',
  outflow_amt DECIMAL(18, 2) DEFAULT NULL COMMENT '流出资金(亿)',
  net_amt DECIMAL(18, 2) DEFAULT NULL COMMENT '净额(亿)',
  company_count INT UNSIGNED DEFAULT NULL,
  leader_stock VARCHAR(64) NOT NULL DEFAULT '',
  leader_change_pct VARCHAR(32) NOT NULL DEFAULT '',
  leader_price VARCHAR(32) NOT NULL DEFAULT '',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (trade_date, period, industry),
  KEY idx_sector_flow_net (trade_date, period, net_amt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
