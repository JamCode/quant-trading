# quant-trading

轻量级**量化交易**项目骨架：数据加载 → 策略信号 → 简单回测。适合在此基础上接真实行情 API、风控与实盘执行。

## 功能

- **策略接口**：实现 `generate_signals(ohlcv)` 返回与价格对齐的信号序列
- **示例策略**：双均线（SMA）交叉
- **回测引擎**：按 bar 回放，手续费/滑点占位，输出权益曲线与基础指标

## 环境

```bash
cd quant-trading
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## 运行示例（合成数据）

```bash
python examples/run_backtest.py
```

## 目录说明

| 路径 | 说明 |
|------|------|
| `src/quant_trading/` | 核心库 |
| `examples/` | 可执行示例 |
| `data/raw/` | 放置 CSV 等本地行情（默认 gitignore） |

## 下一步建议

1. 在 `quant_trading/data/` 中接入券商 / 聚合行情 API，统一成 OHLCV DataFrame  
2. 在 `strategies/` 增加因子与仓位管理（仓位上限、止损等）  
3. 将 `BacktestEngine` 替换或封装为向量回测（如 polars / numba）以提速  

## 许可

MIT
