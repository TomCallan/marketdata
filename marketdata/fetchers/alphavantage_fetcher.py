"""Alpha Vantage Market Data Fetcher."""

import logging
from typing import Optional
import pandas as pd
import requests

from marketdata.config import TIMEFRAME_MAPPINGS, get_api_key
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="alphavantage",
    supported_categories=["stocks", "forex", "crypto", "indices"],
    priority=50,
)
class AlphaVantageFetcher(BaseFetcher):
    """Fetches market data from Alpha Vantage REST API."""

    BASE_URL = "https://www.alphavantage.co/query"

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        api_key = get_api_key("alphavantage")
        if not api_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        cat = instrument.category
        sym = instrument.symbol.upper()

        try:
            if cat in ["stocks", "indices"]:
                return self._fetch_stocks(sym, timeframe, api_key, start, end)
            elif cat == "forex":
                return self._fetch_forex(sym, timeframe, api_key, start, end)
            elif cat == "crypto":
                return self._fetch_crypto(sym, timeframe, api_key, start, end)
        except Exception as e:
            logger.warning(f"Alpha Vantage request failed for {sym}: {e}")

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _fetch_stocks(self, symbol: str, timeframe: str, api_key: str, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
        is_intraday = timeframe in ["1m", "5m", "15m", "30m", "1h"]
        if is_intraday:
            interval = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("av", "60min")
            params = {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol,
                "interval": interval,
                "outputsize": "full",
                "apikey": api_key,
            }
        else:
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": "full",
                "apikey": api_key,
            }

        resp = requests.get(self.BASE_URL, params=params, timeout=10)
        data = resp.json()

        if "Information" in data or "Error Message" in data:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        ts_key = next((k for k in data.keys() if "Time Series" in k), None)
        if not ts_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        records = []
        for ts_str, vals in data[ts_key].items():
            records.append({
                "timestamp": pd.to_datetime(ts_str, utc=True),
                "open": float(vals.get("1. open", 0)),
                "high": float(vals.get("2. high", 0)),
                "low": float(vals.get("3. low", 0)),
                "close": float(vals.get("4. close", 0)),
                "volume": float(vals.get("5. volume", 0)),
            })

        df = pd.DataFrame(records).set_index("timestamp")
        if start:
            df = df[df.index >= pd.to_datetime(start, utc=True)]
        if end:
            df = df[df.index <= pd.to_datetime(end, utc=True)]

        return self.standardize_dataframe(df)

    def _fetch_forex(self, symbol: str, timeframe: str, api_key: str, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
        if len(symbol) != 6:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        from_symbol, to_symbol = symbol[:3], symbol[3:]

        params = {
            "function": "FX_DAILY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "outputsize": "full",
            "apikey": api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=10)
        data = resp.json()

        ts_key = next((k for k in data.keys() if "Time Series FX" in k), None)
        if not ts_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        records = []
        for ts_str, vals in data[ts_key].items():
            records.append({
                "timestamp": pd.to_datetime(ts_str, utc=True),
                "open": float(vals.get("1. open", 0)),
                "high": float(vals.get("2. high", 0)),
                "low": float(vals.get("3. low", 0)),
                "close": float(vals.get("4. close", 0)),
                "volume": 0.0,
            })

        df = pd.DataFrame(records).set_index("timestamp")
        if start:
            df = df[df.index >= pd.to_datetime(start, utc=True)]
        if end:
            df = df[df.index <= pd.to_datetime(end, utc=True)]

        return self.standardize_dataframe(df)

    def _fetch_crypto(self, symbol: str, timeframe: str, api_key: str, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
        coin = symbol.replace("USD", "").replace("USDT", "")
        params = {
            "function": "DIGITAL_CURRENCY_DAILY",
            "symbol": coin,
            "market": "USD",
            "apikey": api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=10)
        data = resp.json()

        ts_key = next((k for k in data.keys() if "Time Series (Digital Currency" in k), None)
        if not ts_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        records = []
        for ts_str, vals in data[ts_key].items():
            records.append({
                "timestamp": pd.to_datetime(ts_str, utc=True),
                "open": float(vals.get("1a. open (USD)", vals.get("1. open", 0))),
                "high": float(vals.get("2a. high (USD)", vals.get("2. high", 0))),
                "low": float(vals.get("3a. low (USD)", vals.get("3. low", 0))),
                "close": float(vals.get("4a. close (USD)", vals.get("4. close", 0))),
                "volume": float(vals.get("5. volume", 0)),
            })

        df = pd.DataFrame(records).set_index("timestamp")
        if start:
            df = df[df.index >= pd.to_datetime(start, utc=True)]
        if end:
            df = df[df.index <= pd.to_datetime(end, utc=True)]

        return self.standardize_dataframe(df)
