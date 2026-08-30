# MarketData: Universal Multi-Asset Market Data Downloader & Cache

A high-performance, modular market data retrieval, caching, and server synchronization toolkit covering **234+ instruments** across **Crypto, Stocks, Commodities, Indices, and Forex**.

---

## 1. Global PC Access & Dynamic Home Directory

MarketData can be installed and queried from **any directory, script, or AI agent** across your entire computer.

### Configuring the Data Directory:
```bash
# View active configuration and cache directory
marketdata config show

# Point the market data cache to any custom folder on your PC
marketdata config set-home C:\Data\marketdata --create

# Or set via environment variable
export MARKETDATA_HOME="C:\Data\marketdata"

# Reset back to default
marketdata config reset-home
```

---

## 2. AI Agent Integration (Antigravity, Claude, Cursor, OpenCode, Kimi)

MarketData includes a built-in **Model Context Protocol (MCP)** server and machine-readable JSON flags for autonomous AI agents.

### Option A: Standard MCP Server Integration
Add MarketData to your agent's MCP configuration (`claude_desktop_config.json`, `.cursor/mcp.json`, or Antigravity):

```json
{
  "mcpServers": {
    "marketdata": {
      "command": "marketdata-mcp",
      "args": []
    }
  }
}
```

#### MCP Tools Provided to Agents:
- **`get_historical_data`**: Retrieve clean OHLCV candlesticks for any asset.
- **`calculate_indicators`**: On-demand computation of SMA (20/50/200), EMA (12/26), RSI (14), MACD, and Bollinger Bands.
- **`get_instrument_info`**: Detailed instrument specifications (leverage, commission, hours, provider mappings).
- **`sync_market_data`**: Automated delta-synchronization of local cache.
- **`list_instruments`**: Browse all 234+ tradeable symbols.
- **`get_cache_status`**: Inspect stored Parquet files, total bars, and disk usage.

### Option B: Machine-Readable JSON CLI
All CLI commands support `--json` for direct parsing by CLI-based agents:
```bash
marketdata get BTCUSD --timeframe 1d --tail 10 --json
marketdata info AAPL --json
marketdata status --json
marketdata sync --timeframe 1h --json
```

---

## 3. Server Cron Jobs & Automated Scheduling

### Running an Incremental Sync:
```bash
# Sync hourly candles for all active markets
marketdata sync --timeframe 1h

# Sync across all 6 timeframes (1d, 1h, 30m, 15m, 5m, 1m)
marketdata sync --all-timeframes

# Sync only crypto (24/7 markets)
marketdata sync --category crypto --timeframe 15m
```

### Auto-Generating Server Cron & Systemd Files:
```bash
marketdata generate-cron
```
This generates:
- `scripts/crontab.txt`: Ready to paste into `crontab -e`.
- `scripts/marketdata-sync.service`: Linux systemd service unit.
- `scripts/marketdata-sync.timer`: Linux systemd recurring timer.

### Running as a Background Daemon:
```bash
# Run continuous background sync every 1 hour (3600 seconds)
marketdata daemon --interval-seconds 3600 --timeframe 1h
```

---

## 4. Loading the Data in Python

### On-Demand Loader (Auto-Cached):
```python
from marketdata.loader import get_historical_data

# Fetch daily crypto data (BTCUSD)
df_btc = get_historical_data("BTCUSD", timeframe="1d", start="2024-01-01")

# Fetch hourly stock data (AAPL)
df_aapl = get_historical_data("AAPL", timeframe="1h")

# Fetch commodity futures (Crude Oil)
df_cl = get_historical_data("CL", timeframe="1d")

# Fetch forex (Euro / US Dollar)
df_eur = get_historical_data("EURUSD", timeframe="1d")
```

---

## 5. Active Market Data Providers

| Priority | Plugin Name | Supported Asset Classes | Key Required? | Description |
| :---: | :--- | :--- | :---: | :--- |
| **5** | **`ccxt`** | Crypto | No | Unified multi-exchange crypto fetcher (Coinbase, Kraken, Gate.io, Bybit, OKX, MEXC). |
| **10** | **`crypto_public`** | Crypto | No | Direct public REST candlestick fallback covering 100% of all altcoin & meme tokens. |
| **20** | **`yfinance`** | Stocks, Forex, Commodities, Indices, Crypto | No | Global coverage for US/global stocks, FX pairs (`=X`), and futures (`CL=F`). |
| **25** | **`massive`** | Stocks, Indices, Forex, Crypto | Optional | Massive (formerly Polygon.io) historical aggregates (`MASSIVE_API_KEY` / `POLYGON_API_KEY`). |
| **25** | **`twelvedata`** | Forex, Commodities, Stocks, Indices, Crypto | Optional | Twelve Data time series (`TWELVEDATA_API_KEY`). |
| **30** | **`tiingo`** | Stocks, Indices, Crypto | Optional | Clean adjusted historical daily equities and crypto (`TIINGO_API_KEY`). |
| **40** | **`finnhub`** | Stocks, Forex, Crypto, Indices | Optional | Fast candle API (60 req/min, `FINNHUB_API_KEY`). |
| **50** | **`alphavantage`** | Stocks, Forex, Crypto, Indices | Optional | US equities, forex, and crypto (`ALPHAVANTAGE_API_KEY`). |
