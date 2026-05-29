-- Global fund stock holdings: overseas tickers + name search (not only A-share 6-digit).
USE fund_svc;

ALTER TABLE fund_holdings
  MODIFY stock_code VARCHAR(32) NOT NULL COMMENT '股票代码（A股6位或海外代码如NVDA）',
  MODIFY stock_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '股票名称';

ALTER TABLE fund_holdings
  ADD KEY idx_fund_holdings_name (stock_name(64));
