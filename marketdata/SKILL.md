---
name: marketdata
description: Universal Multi-Asset Market Data Toolkit for fetching historical OHLCV candles, computing technical indicators, delta-syncing data, and querying instrument leverage and trading hours across Crypto, Stocks, Commodities, Indices, and Forex.
---

# MarketData Agent Skill & Toolkit Reference

Use this skill when you need historical market data, live prices, candlestick charts, technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands), broker leverage specifications, or data synchronization.

---

## 1. Using via Python in Agent Scripts

```python
from marketdata.loader import get_historical_data
from marketdata.mappings import load_ticker_conversions

# 1. Fetch historical OHLCV data (on-demand delta-cached)
df_btc = get_historical_data("BTCUSD", timeframe="1d", start="2024-01-01")
df_aapl = get_historical_data("AAPL", timeframe="1h")
df_oil = get_historical_data("CL", timeframe="1d")
df_eur = get_historical_data("EURUSD", timeframe="1d")

# 2. Inspect Instrument Metadata & Provider Mappings
table = load_ticker_conversions()
btc = table["BTCUSD"]
print(btc.yfinance)  # 'BTC-USD'
print(btc.gateio)    # 'BTC_USDT'
```

---

## 2. Using via CLI (Machine-Readable JSON Mode)

When invoking commands from terminal / bash / subagents, pass `--json` to receive structured JSON:

```bash
# Get historical data in JSON format
marketdata get BTCUSD --timeframe 1d --tail 10 --json

# Get instrument specification & external provider tickers
marketdata info AAPL --json

# List available instruments
marketdata list --category crypto --json

# Check local cache status
marketdata status --json

# Trigger delta-sync
marketdata sync --timeframe 1h --json
```

---

## 3. Using via Model Context Protocol (MCP)

If the `marketdata` MCP server is registered in your agent configuration, use the following tools:
- **`get_historical_data(symbol, timeframe, start, end, limit)`**: Returns latest OHLCV records.
- **`calculate_indicators(symbol, timeframe, indicators, limit)`**: Computes SMA, EMA, RSI, MACD, Bollinger Bands.
- **`get_instrument_info(symbol)`**: Returns leverage limits, commissions, swap rates, and mapped external tickers.
- **`sync_market_data(category, timeframe)`**: Triggers incremental delta-sync.
- **`list_instruments(category)`**: Lists all tradeable instruments.
- **`get_cache_status()`**: Returns current local cache series, counts, and disk usage.

---

## 4. Configuring Global Home Directory

To view or redirect the global shared market data cache to any folder on your PC:
```bash
# View active home directory and data cache paths
marketdata config show

# Set custom global directory (e.g. C:\Data\marketdata)
marketdata config set-home C:\Data\marketdata --create

# Reset back to default
marketdata config reset-home
```
