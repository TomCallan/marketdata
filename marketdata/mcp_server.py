"""MarketData Model Context Protocol (MCP) Server.

Enables AI Agents (Antigravity/AGY, Claude Code, Cursor, OpenCode, Kimi) to
interact with the MarketData toolkit via standard MCP tools.
"""

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from marketdata.cron import CronSyncEngine
from marketdata.loader import DataLoader, get_historical_data
from marketdata.mappings import load_ticker_conversions
from marketdata.registry import get_registry
from marketdata.storage import StorageManager

# Configure logger to output to stderr so stdout remains clean JSON-RPC
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("marketdata.mcp")


# ==============================================================================
# Tool Implementations
# ==============================================================================

def tool_get_historical_data(
    symbol: str,
    timeframe: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Retrieve historical OHLCV data for an instrument."""
    try:
        df = get_historical_data(symbol=symbol, timeframe=timeframe, start=start, end=end)
        if df.empty:
            return {"error": f"No data found for symbol '{symbol}' on timeframe '{timeframe}'."}

        total_bars = len(df)
        display_df = df.tail(limit)

        records = []
        for ts, row in display_df.iterrows():
            records.append({
                "timestamp": str(ts)[:19],
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
                "volume": round(float(row["volume"]), 2),
            })

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "total_bars_available": total_bars,
            "returned_bars_count": len(records),
            "start_timestamp": str(df.index.min())[:19],
            "end_timestamp": str(df.index.max())[:19],
            "latest_close": float(df["close"].iloc[-1]),
            "bars": records,
        }
    except Exception as e:
        return {"error": str(e)}


def tool_sync_market_data(
    category: Optional[str] = None,
    timeframe: str = "1h",
    overlap_bars: int = 2,
    force: bool = False,
) -> Dict[str, Any]:
    """Execute automated incremental delta-sync to update local market data."""
    try:
        engine = CronSyncEngine()
        categories = [category] if category else None
        report = engine.sync(
            categories=categories,
            timeframes=[timeframe],
            overlap_bars=overlap_bars,
            check_market_hours=not force,
            force=force,
        )
        return {
            "status": "success",
            "timestamp": str(report.timestamp)[:19],
            "duration_seconds": round(report.duration_seconds, 2),
            "total_series_evaluated": report.total_series,
            "updated_count": report.updated_count,
            "skipped_closed_count": report.skipped_closed_count,
            "error_count": report.error_count,
            "total_new_bars_added": report.total_bars_added,
        }
    except Exception as e:
        return {"error": str(e)}


def tool_get_instrument_info(symbol: str) -> Dict[str, Any]:
    """Get metadata, leverage limits, trading hours, and external provider tickers for an instrument."""
    try:
        reg = get_registry()
        inst = reg.get(symbol)
        if not inst:
            return {"error": f"Instrument '{symbol}' not found in registry."}

        return {
            "symbol": inst.symbol,
            "category": inst.category,
            "max_leverage_long": inst.max_leverage_long,
            "max_leverage_short": inst.max_leverage_short,
            "commission": inst.commission,
            "trading_hours": inst.trading_hours,
            "overnight_swap": inst.overnight_swap,
            "trading_size": inst.trading_size,
            "mapped_provider_tickers": {
                "yfinance": inst.yfinance_ticker,
                "gateio": inst.gateio_pair,
                "mexc": inst.mexc_symbol,
                "coinbase": inst.coinbase_product,
            },
        }
    except Exception as e:
        return {"error": str(e)}


def tool_list_instruments(category: Optional[str] = None) -> Dict[str, Any]:
    """List available tradeable instruments, optionally filtered by category."""
    try:
        reg = get_registry()
        instruments = reg.list_all(category)
        return {
            "category_filter": category or "all",
            "count": len(instruments),
            "instruments": [
                {
                    "symbol": i.symbol,
                    "category": i.category,
                    "max_leverage": f"{i.max_leverage_long}/{i.max_leverage_short}",
                    "trading_hours": i.trading_hours,
                }
                for i in instruments
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def tool_calculate_indicators(
    symbol: str,
    timeframe: str = "1d",
    indicators: Optional[List[str]] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Calculate standard technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands) on market data."""
    try:
        df = get_historical_data(symbol=symbol, timeframe=timeframe)
        if df.empty:
            return {"error": f"No data found for symbol '{symbol}'."}

        indicators = indicators or ["sma_20", "sma_50", "rsi_14", "macd", "bollinger"]
        ind_lower = [i.lower() for i in indicators]

        # SMA
        if "sma_20" in ind_lower or "sma" in ind_lower:
            df["sma_20"] = df["close"].rolling(20).mean()
        if "sma_50" in ind_lower or "sma" in ind_lower:
            df["sma_50"] = df["close"].rolling(50).mean()
        if "sma_200" in ind_lower:
            df["sma_200"] = df["close"].rolling(200).mean()

        # EMA
        if "ema_12" in ind_lower or "ema" in ind_lower or "macd" in ind_lower:
            df["ema_12"] = df["close"].ewm(span=12, adjust=False).mean()
        if "ema_26" in ind_lower or "ema" in ind_lower or "macd" in ind_lower:
            df["ema_26"] = df["close"].ewm(span=26, adjust=False).mean()

        # MACD
        if "macd" in ind_lower:
            df["macd"] = df["ema_12"] - df["ema_26"]
            df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
            df["macd_hist"] = df["macd"] - df["macd_signal"]

        # RSI (14)
        if "rsi_14" in ind_lower or "rsi" in ind_lower:
            delta = df["close"].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / (avg_loss + 1e-10)
            df["rsi_14"] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        if "bollinger" in ind_lower or "bb" in ind_lower:
            if "sma_20" not in df.columns:
                df["sma_20"] = df["close"].rolling(20).mean()
            std = df["close"].rolling(20).std()
            df["bb_upper"] = df["sma_20"] + (std * 2)
            df["bb_lower"] = df["sma_20"] - (std * 2)

        display_df = df.tail(limit).dropna()
        records = []
        for ts, row in display_df.iterrows():
            rec = {"timestamp": str(ts)[:19]}
            for col in df.columns:
                val = row[col]
                rec[col] = round(float(val), 4) if pd.notnull(val) else None
            records.append(rec)

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "indicators_calculated": [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]],
            "returned_bars_count": len(records),
            "latest_indicators": records[-1] if records else {},
            "history": records,
        }
    except Exception as e:
        return {"error": str(e)}


def tool_get_cache_status() -> Dict[str, Any]:
    """Inspect status of local Parquet market data cache."""
    try:
        storage = StorageManager()
        cached = storage.list_cached_info()
        total_size = sum(c.file_size_bytes for c in cached)
        total_bars = sum(c.row_count for c in cached)
        return {
            "total_files": len(cached),
            "total_bars": total_bars,
            "total_disk_bytes": total_size,
            "total_disk_mb": round(total_size / (1024 * 1024), 2),
            "series": [
                {
                    "symbol": c.symbol,
                    "category": c.category,
                    "timeframe": c.timeframe,
                    "bars": c.row_count,
                    "start": str(c.start)[:19],
                    "end": str(c.end)[:19],
                }
                for c in sorted(cached, key=lambda x: (x.category, x.symbol, x.timeframe))
            ],
        }
    except Exception as e:
        return {"error": str(e)}


# ==============================================================================
# MCP Protocol Definitions
# ==============================================================================

TOOLS_MANIFEST = [
    {
        "name": "get_historical_data",
        "description": "Fetch on-demand historical OHLCV candlestick data for any asset (crypto, stocks, forex, commodities, indices). Automatically retrieves and delta-syncs from cache.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Asset ticker (e.g., 'BTCUSD', 'AAPL', 'CL', 'EURUSD', 'SPY')"},
                "timeframe": {"type": "string", "description": "Candle timeframe: '1m', '5m', '15m', '30m', '1h', '4h', '1d'", "default": "1d"},
                "start": {"type": "string", "description": "Start date/time (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)"},
                "end": {"type": "string", "description": "End date/time (YYYY-MM-DD)"},
                "limit": {"type": "integer", "description": "Maximum number of most recent bars to return (default: 50)", "default": 50},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "sync_market_data",
        "description": "Trigger an incremental delta-sync on local cached market data to pull missing bars from remote APIs with safety overlap and market hours checking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["crypto", "stocks", "commodities", "indices", "forex"], "description": "Asset category filter"},
                "timeframe": {"type": "string", "description": "Timeframe to sync (default: '1h')", "default": "1h"},
                "overlap_bars": {"type": "integer", "description": "Overlap buffer bars to ensure candle finalization", "default": 2},
                "force": {"type": "boolean", "description": "Force sync even if market is closed", "default": False},
            },
        },
    },
    {
        "name": "get_instrument_info",
        "description": "Get detailed instrument specification including leverage limits, commissions, overnight swap, trading hours, and mapped external provider tickers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Asset symbol (e.g. 'BTCUSD', 'CL', 'EURUSD', 'AAPL')"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "list_instruments",
        "description": "List all 234+ tradeable instruments across Crypto, Stocks, Commodities, Indices, and Forex.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["crypto", "stocks", "commodities", "indices", "forex"], "description": "Filter by asset class"},
            },
        },
    },
    {
        "name": "calculate_indicators",
        "description": "Calculate standard technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands) for any asset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Asset symbol (e.g., 'BTCUSD', 'AAPL')"},
                "timeframe": {"type": "string", "description": "Candle timeframe: '1m', '5m', '15m', '1h', '1d'", "default": "1d"},
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of indicators to compute: 'sma_20', 'sma_50', 'sma_200', 'rsi_14', 'macd', 'bollinger'",
                },
                "limit": {"type": "integer", "description": "Number of recent bars to return (default: 50)", "default": 50},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_cache_status",
        "description": "Inspect all local Parquet cached market data series, date ranges, total bar counts, and disk usage.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def handle_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Dispatches tool execution to the matching function."""
    if tool_name == "get_historical_data":
        return tool_get_historical_data(
            symbol=arguments["symbol"],
            timeframe=arguments.get("timeframe", "1d"),
            start=arguments.get("start"),
            end=arguments.get("end"),
            limit=arguments.get("limit", 50),
        )
    elif tool_name == "sync_market_data":
        return tool_sync_market_data(
            category=arguments.get("category"),
            timeframe=arguments.get("timeframe", "1h"),
            overlap_bars=arguments.get("overlap_bars", 2),
            force=arguments.get("force", False),
        )
    elif tool_name == "get_instrument_info":
        return tool_get_instrument_info(symbol=arguments["symbol"])
    elif tool_name == "list_instruments":
        return tool_list_instruments(category=arguments.get("category"))
    elif tool_name == "calculate_indicators":
        return tool_calculate_indicators(
            symbol=arguments["symbol"],
            timeframe=arguments.get("timeframe", "1d"),
            indicators=arguments.get("indicators"),
            limit=arguments.get("limit", 50),
        )
    elif tool_name == "get_cache_status":
        return tool_get_cache_status()
    else:
        raise ValueError(f"Unknown tool name: '{tool_name}'")


# ==============================================================================
# JSON-RPC Stdio Server Loop
# ==============================================================================

def run_mcp_server():
    """Main JSON-RPC stdio server loop for Model Context Protocol."""
    logger.info("MarketData MCP Server running on stdio...")

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue

            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # 1. Initialize
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": "marketdata",
                            "version": "0.1.0",
                        },
                        "capabilities": {
                            "tools": {},
                        },
                    },
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            # 2. Initialized notification
            elif method == "notifications/initialized":
                pass

            # 3. Ping
            elif method == "ping":
                response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            # 4. List Tools
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS_MANIFEST,
                    },
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            # 5. Call Tool
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})

                try:
                    res_data = handle_tool_call(tool_name, tool_args)
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(res_data, indent=2),
                                }
                            ],
                        },
                    }
                except Exception as e:
                    logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32603,
                            "message": str(e),
                        },
                    }

                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            else:
                # Method not found
                if req_id is not None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method '{method}' not found",
                        },
                    }
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

        except Exception as e:
            logger.error(f"Unhandled MCP server exception: {e}", exc_info=True)


if __name__ == "__main__":
    run_mcp_server()
