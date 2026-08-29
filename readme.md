# MarketData: Universal Multi-Asset Market Data Downloader & Cache

A high-performance, modular market data retrieval, caching, and server synchronization toolkit covering **234+ instruments** across **Crypto, Stocks, Commodities, Indices, and Forex**.

---

## 1. Features
- **Zero-Key Out-Of-The-Box Operation**: Retrieves historical and live candles without mandatory API keys using CCXT, Gate.io, MEXC, Coinbase, and Yahoo Finance.
- **8 Modular Provider Plugins**: Transparent priority routing with support for **Massive (formerly Polygon.io)**, **Twelve Data**, **Tiingo**, **Finnhub**, and **Alpha Vantage**.
- **Server Cron Optimization**: Smart incremental delta-syncing (`sync`) that checks local caches, fetches only missing candle slices (with 2-bar overlap for candle finalization), and skips closed markets (e.g. weekends) in 0.00 seconds.
- **Crash-Resilient Storage**: Atomic Parquet writes (`.tmp` -> atomic rename) guaranteeing zero database/file corruption during power outages or interrupted jobs.
- **Built-in Daemon & Deployment Generators**: One command to generate ready-to-run Crontab schedules and Linux systemd `.service` / `.timer` units.

---

## 2. Server Cron Jobs & Automated Scheduling

### Running an Incremental Sync:
```bash
# Sync hourly candles for all active markets
python -m marketdata.data sync --timeframe 1h

# Sync across all 6 timeframes (1d, 1h, 30m, 15m, 5m, 1m)
python -m marketdata.data sync --all-timeframes

# Sync only crypto (24/7 markets)
python -m marketdata.data sync --category crypto --timeframe 15m
```

### Auto-Generating Server Cron & Systemd Files:
```bash
python -m marketdata.data generate-cron
```
This generates:
- `scripts/crontab.txt`: Ready to paste into `crontab -e`.
- `scripts/marketdata-sync.service`: Linux systemd service unit.
- `scripts/marketdata-sync.timer`: Linux systemd recurring timer.

### Running as a Background Daemon:
```bash
# Run continuous background sync every 1 hour (3600 seconds)
python -m marketdata.data daemon --interval-seconds 3600 --timeframe 1h
```

---

## 3. Loading the Data in Python

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

### Direct Parquet Access (Pandas / Polars / DuckDB):
```python
import pandas as pd
import polars as pl
import duckdb

# 1. Pandas
df = pd.read_parquet("data/crypto/BTCUSD_1d.parquet")

# 2. Polars
df_pl = pl.read_parquet("data/stocks/AAPL_1d.parquet")

# 3. DuckDB SQL
res = duckdb.query("""
    SELECT timestamp, close, volume 
    FROM 'data/commodities/CL_1d.parquet' 
    ORDER BY timestamp DESC LIMIT 10
""").df()
```

---

## 4. Active Market Data Providers

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

---

## 5. CLI Commands Quick Reference

```bash
# Check registered market data sources
python -m marketdata.data sources

# Check configured API keys status
python -m marketdata.data keys

# Check local cache storage and bar counts
python -m marketdata.data status

# List all tradeable instruments
python -m marketdata.data list --category commodities

# Show instrument details & mapped external tickers
python -m marketdata.data info CL

# Translate tickers
python -m marketdata.data convert BTCUSD --provider yfinance
```
