"""Configuration, paths, and API key management for MarketData toolkit."""

import os
from pathlib import Path
from typing import Optional

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
INFO_FILE = BASE_DIR / "info.md"

# Ensure data and logs directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Standard timeframes
TIMEFRAME_MAPPINGS = {
    "1m": {"yf": "1m", "gate": "1m", "mexc": "1m", "coinbase": 60, "ccxt": "1m", "av": "1min", "finnhub": "1", "polygon": "1/minute", "twelvedata": "1min"},
    "5m": {"yf": "5m", "gate": "5m", "mexc": "5m", "coinbase": 300, "ccxt": "5m", "av": "5min", "finnhub": "5", "polygon": "5/minute", "twelvedata": "5min"},
    "15m": {"yf": "15m", "gate": "15m", "mexc": "15m", "coinbase": 900, "ccxt": "15m", "av": "15min", "finnhub": "15", "polygon": "15/minute", "twelvedata": "15min"},
    "30m": {"yf": "30m", "gate": "30m", "mexc": "30m", "coinbase": 1800, "ccxt": "30m", "av": "30min", "finnhub": "30", "polygon": "30/minute", "twelvedata": "30min"},
    "1h": {"yf": "1h", "gate": "1h", "mexc": "60m", "coinbase": 3600, "ccxt": "1h", "av": "60min", "finnhub": "60", "polygon": "1/hour", "twelvedata": "1h"},
    "4h": {"yf": "4h", "gate": "4h", "mexc": "4h", "coinbase": 21600, "ccxt": "4h", "av": None, "finnhub": None, "polygon": "4/hour", "twelvedata": "4h"},
    "1d": {"yf": "1d", "gate": "1d", "mexc": "1d", "coinbase": 86400, "ccxt": "1d", "av": "DAILY", "finnhub": "D", "polygon": "1/day", "twelvedata": "1day"},
}

DEFAULT_COLUMNS = ["open", "high", "low", "close", "volume"]


def get_api_key(service_name: str) -> Optional[str]:
    """
    Retrieve API key for external providers from environment variables or .env file.
    Example services: 'alphavantage', 'finnhub', 'tiingo', 'massive', 'polygon', 'twelvedata'.
    """
    aliases = [service_name]
    if service_name.lower() in ["polygon", "massive"]:
        aliases = ["MASSIVE", "POLYGON"]

    for name in aliases:
        env_var_name = f"{name.upper()}_API_KEY"
        key = os.environ.get(env_var_name)
        if key:
            return key.strip()

    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    for name in aliases:
                        env_var_name = f"{name.upper()}_API_KEY"
                        if line.startswith(f"{env_var_name}="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
        except Exception:
            pass

    return None
