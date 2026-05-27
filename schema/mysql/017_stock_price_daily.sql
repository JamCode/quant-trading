-- Per-stock daily OHLCV (lazy-filled on first API request, qfq).
USE fund_svc;

CREATE TABLE IF NOT EXISTS stock_price_daily (
  code VARCHAR(6) NOT NULL COMMENT '股票代码',
  trade_date DATE NOT NULL COMMENT '交易日',
  open DECIMAL(14, 4) DEFAULT NULL,
  high DECIMAL(14, 4) DEFAULT NULL,
  low DECIMAL(14, 4) DEFAULT NULL,
  close DECIMAL(14, 4) DEFAULT NULL,
  volume BIGINT DEFAULT NULL COMMENT '成交量(股)',
  amount DECIMAL(18, 2) DEFAULT NULL COMMENT '成交额',
  change_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨跌幅%',
  PRIMARY KEY (code, trade_date),
  KEY idx_stock_price_code_date (code, trade_date DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
