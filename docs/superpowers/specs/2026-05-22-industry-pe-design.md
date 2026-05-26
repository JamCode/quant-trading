# 行业平均 PE（巨潮国证）— 设计说明

**日期：** 2026-05-22  
**状态：** 已批准  
**页面：** `/valuation`（与宽基 PE 同页 Tab）  
**数据源：** 巨潮资讯 CNINFO · 国证行业分类

## 概述

从 AkShare `stock_industry_pe_ratio_cninfo(symbol="国证行业分类", date=YYYYMMDD)` 拉取**官方行业静态市盈率**（算术平均 / 中位数 / 加权平均），写入 MySQL，并在估值页展示最新值与历史折线。

不与同花顺行业资金流行业名对齐；以数据源可用性与历史可回填为准。

## 目标

- 每日定时同步当日（最近交易日）国证全行业 PE 快照。
- 一次性初始化脚本：自 **2023-01-01** 起按日回填（无数据日跳过）。
- Web：在 `/valuation` 增加 **「行业 PE」** Tab，表格 + 历史图。

## 明确不做

- 成分股自算加权 PE。
- 挂接到 `sector_fund_flow_daily` 后续步骤。
- 证监会分类（v1 仅国证；以后可加 Tab）。
- TTM / 动态 PE（巨潮接口仅静态口径）。

## 数据模型

### 迁移 `schema/mysql/014_industry_pe_daily.sql`

表 `industry_pe_daily`：

| 列 | 说明 |
|----|------|
| `trade_date` | 变动日期（与 CNINFO `变动日期` 一致） |
| `industry_code` | 巨潮 `行业编码` |
| `industry_name` | 行业名称 |
| `industry_level` | 1–4 层级 |
| `pe_weighted` | 静态市盈率-加权平均 |
| `pe_median` | 静态市盈率-中位数 |
| `pe_avg` | 静态市盈率-算术平均 |
| `company_count` | 公司数量 |
| `calc_company_count` | 纳入计算公司数量 |
| `source` | 固定 `cninfo_gics` |
| `updated_at` | UTC 写入时间 |

主键：`(trade_date, industry_code)`。

### 爬虫任务

- `task_key`: `industry_pe_cninfo_daily_sync`
- 调度：工作日 cron，默认 **18:20**（可 env 配置）
- 逻辑：对「今日」及必要时最近交易日调用 CNINFO 一次，UPSERT 全量行

## 回填脚本

- 路径：`examples/backfill_industry_pe_cninfo.py`
- 参数：`--start 2023-01-01`（默认）、`--end`（默认今天）、`--delay` 秒
- 遍历日历日，空响应/错误计入 `skipped`，不中断整批

## API / Web

- `GET /api/valuation/industry` — 最新 PE（可选 `level`、`limit`）
- `GET /api/valuation/industry/history` — `industry_code` + 可选 `limit`
- `/valuation?tab=industry` — 行业 Tab；`tab=index` 为宽基（默认）

## 错误处理

- 单日 CNINFO 无记录：跳过，记 warning。
- 部分字段缺失：允许 NULL，行仍写入。
- 定时任务：至少 1 行成功则 `ok: true`；全日无数据则 `ok: false` 并带 error。

## 依赖

- Python：`akshare`（已有 crawler extra）
- 无新 pip 包
