"""Twelve Data Market Data Fetcher."""

import logging
from typing import Optional
import pandas as pd
import requests

from marketdata.config import TIMEFRAME_MAPPINGS, get_api_key
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="twelvedata",
    supported_categories=["forex", "commodities", "stocks", "indices", "crypto"],
    priority=25,
)
class TwelveDataFetcher(BaseFetcher):
    """Fetches time series from Twelve Data REST API."""

    BASE_URL = "https://api.twelvedata.com/time_series"

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        api_key = get_api_key("twelvedata")
        if not api_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        cat = instrument.category
        sym = instrument.symbol.upper()
        td_interval = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("twelvedata", "1day")

        # Format symbol for Twelve Data
        if cat == "forex":
            td_symbol = f"{sym[:3]}/{sym[3:]}" if len(sym) == 6 else sym
        elif cat == "crypto":
            coin = sym.replace("USD", "").replace("USDT", "")
            td_symbol = f"{coin}/USD"
        elif cat == "commodities":
            td_map = {"CL": "WTI/USD", "XAU": "XAU/USD", "XAG": "XAG/USD", "XPT": "XPT/USD", "XPD": "XPD/USD", "COPPER": "COPPER/USD", "NATGAS": "NG/USD"}
            td_symbol = td_map.get(sym, f"{sym}/USD")
        else:
            td_symbol = sym

        params = {
            "symbol": td_symbol,
            "interval": td_interval,
            "outputsize": 5000,
            "apikey": api_key,
        }
        if start:
            params["start_date"] = pd.to_datetime(start, utc=True).strftime("%Y-%m-%d %H:%M:%S")
        if end:
            params["end_date"] = pd.to_datetime(end, utc=True).strftime("%Y-%m-%d %H:%M:%S")

        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            if resp.status_code != 200:
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            data = resp.json()
            if data.get("status") == "error" or not data.get("values"):
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            records = []
            for row in data["values"]:
                records.append({
                    "timestamp": pd.to_datetime(row["datetime"], utc=True),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0) or 0.0),
                })

            df = pd.DataFrame(records).set_index("timestamp")
            return self.standardize_dataframe(df)

        except Exception as e:
            logger.warning(f"Twelve Data request failed for {sym}: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
