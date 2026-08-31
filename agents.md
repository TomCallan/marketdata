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
- **AI Agent MCP Server**: Full Model Context Protocol (MCP) server support (`marketdata mcp` / `marketdata-mcp`) allowing AI agents (Antigravity, Claude, Cursor, OpenCode, Kimi) to fetch candles and calculate indicators.
- **Global Home Directory Configuration**: Configurable via CLI (`marketdata config set-home <path>`) or `MARKETDATA_HOME` environment variable.

---

## 3. Global CLI Usage & Machine-Readable Output

```bash
# Manage active home directory & data paths
marketdata config show
marketdata config set-home C:\Data\marketdata --create
marketdata config reset-home

# Start MCP Server on stdio for AI agents
marketdata mcp

# Get data in machine-readable JSON format for AI agents
marketdata get BTCUSD --timeframe 1d --tail 10 --json
marketdata info AAPL --json
marketdata list --category crypto --json
marketdata status --json
marketdata sync --timeframe 1h --json

# Execute server cron delta-sync
marketdata sync --timeframe 1h
marketdata sync --all-timeframes

# Run persistent sync daemon
marketdata daemon --interval-seconds 3600

# Windows System Tray popup app & startup management
marketdata tray
marketdata tray --install-startup
marketdata tray --remove-startup
marketdata tray --status
marketdata tray --explore

# Generate Crontab and Systemd deployment templates
marketdata generate-cron
```

---

## 4. Model Context Protocol (MCP) Server Setup

Add this configuration to your AI agent's config file (e.g. `claude_desktop_config.json`, `.cursor/mcp.json`, or Antigravity):

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

### Available MCP Tools for Agents:
- **`get_historical_data(symbol, timeframe, start, end, limit)`**: Fetch OHLCV candles.
- **`calculate_indicators(symbol, timeframe, indicators, limit)`**: Compute SMA, EMA, RSI, MACD, Bollinger Bands.
- **`get_instrument_info(symbol)`**: Leverage limits, trading hours, and external provider mappings.
- **`sync_market_data(category, timeframe)`**: Run delta-sync.
- **`list_instruments(category)`**: List available instruments.
- **`get_cache_status()`**: Inspect cached datasets and disk usage.