-- Fund holdings, stock-industry map, industry exposure, metrics for dashboard.
USE fund_svc;

CREATE TABLE IF NOT EXISTS stock_ths_industry (
  trade_date DATE NOT NULL,
  code VARCHAR(6) NOT NULL,
  industry VARCHAR(64) NOT NULL,
  PRIMARY KEY (trade_date, code),
  KEY idx_stock_ths_industry_ind (trade_date, industry)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fund_holdings_jobs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  funds_target INT UNSIGNED DEFAULT NULL,
  funds_ok INT UNSIGNED DEFAULT NULL,
  funds_failed INT UNSIGNED DEFAULT NULL,
  ok TINYINT(1) NOT NULL DEFAULT 0,
  error TEXT,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fund_holdings (
  fund_code VARCHAR(16) NOT NULL,
  report_date VARCHAR(32) NOT NULL COMMENT '如 2024年1季度',
  stock_code VARCHAR(6) NOT NULL,
  stock_name VARCHAR(64) NOT NULL DEFAULT '',
  weight_pct DECIMAL(10, 4) DEFAULT NULL COMMENT '占净值比例%',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (fund_code, report_date, stock_code),
  KEY idx_fund_holdings_code (fund_code),
  KEY idx_fund_holdings_stock (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fund_industry_exposure (
  fund_code VARCHAR(16) NOT NULL,
  report_date VARCHAR(32) NOT NULL,
  industry VARCHAR(64) NOT NULL,
  weight_pct DECIMAL(10, 4) NOT NULL COMMENT '行业股票持仓占净值合计%',
  stock_count INT UNSIGNED DEFAULT NULL,
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (fund_code, report_date, industry),
  KEY idx_fund_exp_industry (industry, weight_pct DESC),
  KEY idx_fund_exp_fund (fund_code, weight_pct DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fund_metrics (
  fund_code VARCHAR(16) NOT NULL PRIMARY KEY,
  return_1m DECIMAL(12, 4) DEFAULT NULL COMMENT '近1月收益率%',
  return_3m DECIMAL(12, 4) DEFAULT NULL COMMENT '近3月收益率%',
  return_1y DECIMAL(12, 4) DEFAULT NULL COMMENT '近1年收益率%',
  rank_in_type INT UNSIGNED DEFAULT NULL COMMENT '同类排名(越小越好)',
  aum DECIMAL(18, 2) DEFAULT NULL COMMENT '规模(亿,可选)',
  updated_at DATETIME(3) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
