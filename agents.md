# MarketData Toolkit & Agent Architecture Guide

## 1. Tradeable Assets & Trading Conditions
- For full broker instrument specifications, leverage limits, trading hours, overnight swaps, and commissions, see [`info.md`](info.md).
- For complete bidirectional ticker conversions across all 234+ assets to Yahoo Finance, Gate.io, MEXC, and Coinbase, see [`TICKER_CONVERSION_TABLE.md`](TICKER_CONVERSION_TABLE.md) and [`ticker_mappings.json`](ticker_mappings.json).

---

## 2. On-Demand Market Data Architecture

All historical market data is retrieved **on-demand** using high-availability free providers and cached locally in high-performance **Parquet** format (`data/<category>/<symbol>_<timeframe>.parquet`).

### Active Data Source Plugins:
1. **`ccxt`** (Priority 5, Zero-Key): Unified multi-exchange crypto fetcher (Coinbase, Kraken, Gate.io, Bybit, OKX, MEXC).
2. **`crypto_public`** (Priority 10, Zero-Key): Public REST candlestick endpoints covering 100% of all altcoin & meme tokens in `info.md`.
3. **`yfinance`** (Priority 20, Zero-Key): Global stocks, ETFs, forex (all 39 pairs via `=X`), commodity futures (`CL=F`, `GC=F`, etc.), and indices.
4. **`massive`** (Priority 25, Free Key Optional): Massive (formerly Polygon.io) US equities, forex, and crypto historical aggregates (`MASSIVE_API_KEY` / `POLYGON_API_KEY`).
5. **`twelvedata`** (Priority 25, Free Key Optional): Twelve Data Forex, Commodities, Equities, Indices, Crypto (`TWELVEDATA_API_KEY`).
6. **`tiingo`** (Priority 30, Free Key Optional): High-quality IEX historical daily equities and crypto (`TIINGO_API_KEY`).
7. **`finnhub`** (Priority 40, Free Key Optional): Fast historical candle data (`FINNHUB_API_KEY`).
8. **`alphavantage`** (Priority 50, Free Key Optional): US equities, forex, and crypto (`ALPHAVANTAGE_API_KEY`).

### Key Features:
- **Zero API Key Requirement**: Primary and secondary fetchers operate out-of-the-box without keys.
- **Transparent Fallback Chain**: If an API key is missing or rate-limited, requests automatically cascade to subsequent free/zero-key providers.
- **Server Cron Delta-Sync Engine**: High-efficiency incremental synchronization that only pulls missing candle slices, skips closed markets, and performs atomic Parquet writes.
- **Unified OHLCV Schema**: UTC `timestamp` index with columns `['open', 'high', 'low', 'close', 'volume']`.

---

## 3. Python API Quickstart

### Fetching Historical Data:
```python
from marketdata.loader import get_historical_data

# Fetch daily crypto data (auto-routes to CCXT -> Gate.io -> Yahoo)
df_btc = get_historical_data("BTCUSD", timeframe="1d", start="2024-01-01")

# Fetch hourly stock data
df_aapl = get_historical_data("AAPL", timeframe="1h")

# Fetch commodity futures (Crude Oil)
df_cl = get_historical_data("CL", timeframe="1d")

# Fetch forex (Euro / US Dollar)
df_eur = get_historical_data("EURUSD", timeframe="1d")
```

### Running Server Incremental Sync:
```python
from marketdata.cron import CronSyncEngine

engine = CronSyncEngine()
# Incremental delta-sync with closed market skipping
report = engine.sync(timeframes=["1h", "1d"], overlap_bars=2)
print(f"Updated {report.updated_count} series, added {report.total_bars_added} bars.")
```

---

## 4. CLI Usage (`python -m marketdata.data`)

```bash
# Execute server cron delta-sync
python -m marketdata.data sync --timeframe 1h
python -m marketdata.data sync --all-timeframes

# Run persistent sync daemon
python -m marketdata.data daemon --interval-seconds 3600

# Generate Crontab and Systemd deployment templates
python -m marketdata.data generate-cron

# List all tradeable instruments (or filter by category)
python -m marketdata.data list --category crypto

# Show instrument details & mapped external tickers
python -m marketdata.data info BTCUSD

# Fetch and cache historical data on demand
python -m marketdata.data get BTCUSD --timeframe 1d --start 2024-01-01

# Check local cache storage and bar counts
python -m marketdata.data status

# List active market data plugins/sources
python -m marketdata.data sources

# Check optional API keys status
python -m marketdata.data keys
```