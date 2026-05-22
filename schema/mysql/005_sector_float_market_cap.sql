-- Industry float market cap: sum of THS constituent 流通市值 (亿元), daily with sector flow.
USE fund_svc;

ALTER TABLE sector_fund_flow
  ADD COLUMN float_market_cap DECIMAL(18, 2) DEFAULT NULL
    COMMENT '成分股流通市值合计(亿),同花顺thshy加总'
  AFTER company_count;
