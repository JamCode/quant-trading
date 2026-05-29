-- Per-stock industry on daily snapshot (East Money 个股资料).
USE fund_svc;

ALTER TABLE stock_daily
  ADD COLUMN industry VARCHAR(64) DEFAULT NULL COMMENT '行业(东财)' AFTER name,
  ADD KEY idx_stock_daily_industry (trade_date, industry);
