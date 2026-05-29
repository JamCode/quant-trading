USE fund_svc;

CREATE TABLE IF NOT EXISTS stock_basic (
  code VARCHAR(6) NOT NULL,
  name VARCHAR(64) NOT NULL DEFAULT '',
  industry VARCHAR(64) DEFAULT NULL COMMENT '行业(东财)',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (code),
  KEY idx_stock_basic_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO stock_basic (code, name, industry, updated_at)
SELECT sd.code, sd.name, sd.industry, sd.updated_at
FROM stock_daily sd
INNER JOIN (
  SELECT code, MAX(trade_date) AS trade_date
  FROM stock_daily
  GROUP BY code
) latest ON latest.code = sd.code AND latest.trade_date = sd.trade_date
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  industry = COALESCE(VALUES(industry), stock_basic.industry),
  updated_at = VALUES(updated_at);
