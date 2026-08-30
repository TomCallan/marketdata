"""Configuration, paths, and API key management for MarketData toolkit.

Supports dynamic home directory configuration via:
1. MARKETDATA_HOME environment variable
2. User config file (~/.marketdatarc or ~/.marketdata/config.json)
3. Default project repository directory
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Default repository directory
DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent

# User configuration file path in user's home directory
USER_CONFIG_FILE = Path.home() / ".marketdatarc"


def get_user_config() -> Dict[str, Any]:
    """Reads persistent user configuration from ~/.marketdatarc."""
    if USER_CONFIG_FILE.exists():
        try:
            with open(USER_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def set_user_config_value(key: str, value: Any) -> None:
    """Updates a persistent configuration key in ~/.marketdatarc."""
    cfg = get_user_config()
    cfg[key] = value
    try:
        with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        raise IOError(f"Failed to write configuration to {USER_CONFIG_FILE}: {e}")


def get_home_dir() -> Path:
    """
    Resolves the active MarketData home directory.
    Priority:
    1. MARKETDATA_HOME environment variable
    2. 'home_dir' entry in ~/.marketdatarc
    3. DEFAULT_BASE_DIR (current repository directory)
    """
    env_home = os.environ.get("MARKETDATA_HOME")
    if env_home and Path(env_home).exists():
        return Path(env_home).resolve()

    cfg = get_user_config()
    cfg_home = cfg.get("home_dir")
    if cfg_home and Path(cfg_home).exists():
        return Path(cfg_home).resolve()

    return DEFAULT_BASE_DIR


# Active dynamic base paths
BASE_DIR = get_home_dir()
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
INFO_FILE = DEFAULT_BASE_DIR / "info.md" if not (BASE_DIR / "info.md").exists() else BASE_DIR / "info.md"

# Ensure directories exist
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
    Retrieve API key for external providers from environment variables or .env files.
    Checks environment variables first, then BASE_DIR/.env, then DEFAULT_BASE_DIR/.env.
    """
    aliases = [service_name]
    if service_name.lower() in ["polygon", "massive"]:
        aliases = ["MASSIVE", "POLYGON"]

    for name in aliases:
        env_var_name = f"{name.upper()}_API_KEY"
        key = os.environ.get(env_var_name)
        if key:
            return key.strip()

    # Search in .env files
    env_candidates = [
        get_home_dir() / ".env",
        DEFAULT_BASE_DIR / ".env",
    ]
    for env_file in env_candidates:
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
