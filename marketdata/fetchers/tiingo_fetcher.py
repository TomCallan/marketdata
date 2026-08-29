"""Tiingo Market Data Fetcher."""

import logging
from typing import Optional
import pandas as pd
import requests

from marketdata.config import get_api_key
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="tiingo",
    supported_categories=["stocks", "indices", "crypto"],
    priority=30,
)
class TiingoFetcher(BaseFetcher):
    """Fetches market data from Tiingo REST API."""

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        api_key = get_api_key("tiingo")
        if not api_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        cat = instrument.category
        sym = instrument.symbol.upper()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {api_key}",
        }

        try:
            if cat in ["stocks", "indices"]:
                url = f"https://api.tiingo.com/tiingo/daily/{sym.lower()}/prices"
                params = {}
                if start:
                    params["startDate"] = pd.to_datetime(start, utc=True).strftime("%Y-%m-%d")
                if end:
                    params["endDate"] = pd.to_datetime(end, utc=True).strftime("%Y-%m-%d")

                resp = requests.get(url, headers=headers, params=params, timeout=10)
                if resp.status_code != 200:
                    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

                raw = resp.json()
                if not isinstance(raw, list) or not raw:
                    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

                df = pd.DataFrame(raw)
                df["timestamp"] = pd.to_datetime(df["date"], utc=True)
                df = df.set_index("timestamp")

                if "adjClose" in df.columns:
                    df["close"] = df["adjClose"]
                if "adjOpen" in df.columns:
                    df["open"] = df["adjOpen"]
                if "adjHigh" in df.columns:
                    df["high"] = df["adjHigh"]
                if "adjLow" in df.columns:
                    df["low"] = df["adjLow"]

                return self.standardize_dataframe(df)

            elif cat == "crypto":
                coin = sym.replace("USD", "").replace("USDT", "")
                url = "https://api.tiingo.com/tiingo/crypto/prices"
                params = {
                    "tickers": f"{coin.lower()}usd",
                    "resampleFreq": "1day" if timeframe == "1d" else "1hour",
                }
                if start:
                    params["startDate"] = pd.to_datetime(start, utc=True).strftime("%Y-%m-%d")
                if end:
                    params["endDate"] = pd.to_datetime(end, utc=True).strftime("%Y-%m-%d")

                resp = requests.get(url, headers=headers, params=params, timeout=10)
                if resp.status_code != 200:
                    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

                raw = resp.json()
                if not isinstance(raw, list) or not raw or "priceData" not in raw[0]:
                    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

                df = pd.DataFrame(raw[0]["priceData"])
                df["timestamp"] = pd.to_datetime(df["date"], utc=True)
                df = df.set_index("timestamp")

                return self.standardize_dataframe(df)

        except Exception as e:
            logger.warning(f"Tiingo request failed for {sym}: {e}")

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
