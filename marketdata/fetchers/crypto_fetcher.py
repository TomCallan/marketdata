"""High-coverage Free Public Crypto Fetcher."""

import logging
from typing import List, Optional
import pandas as pd
import requests

from marketdata.config import TIMEFRAME_MAPPINGS
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="crypto_public",
    supported_categories=["crypto"],
    priority=10,
)
class CryptoPublicFetcher(BaseFetcher):
    """Fetches crypto data from public endpoints with automatic provider fallback."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        providers = [
            self._fetch_gateio,
            self._fetch_mexc,
            self._fetch_coinbase,
        ]

        for fetcher_func in providers:
            try:
                df = fetcher_func(instrument, timeframe, start, end)
                if df is not None and not df.empty:
                    return self.standardize_dataframe(df)
            except Exception as e:
                logger.debug(f"{fetcher_func.__name__} failed for {instrument.symbol}: {e}")
                continue

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def _fetch_gateio(
        self,
        instrument: Instrument,
        timeframe: str,
        start: Optional[str],
        end: Optional[str],
    ) -> Optional[pd.DataFrame]:
        pair = instrument.gateio_pair
        if not pair:
            return None

        interval = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("gate", "1d")
        url = "https://api.gateio.ws/api/v4/spot/candlesticks"

        params = {
            "currency_pair": pair,
            "interval": interval,
            "limit": 1000,
        }
        if start:
            params["from"] = int(pd.to_datetime(start, utc=True).timestamp())
        if end:
            params["to"] = int(pd.to_datetime(end, utc=True).timestamp())

        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            return None

        raw = resp.json()
        if not isinstance(raw, list) or len(raw) == 0:
            return None

        records = []
        for row in raw:
            try:
                ts = pd.to_datetime(int(row[0]), unit="s", utc=True)
                records.append({
                    "timestamp": ts,
                    "open": float(row[5]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "close": float(row[2]),
                    "volume": float(row[6]),
                })
            except (ValueError, IndexError):
                continue

        if not records:
            return None

        return pd.DataFrame(records).set_index("timestamp")

    def _fetch_mexc(
        self,
        instrument: Instrument,
        timeframe: str,
        start: Optional[str],
        end: Optional[str],
    ) -> Optional[pd.DataFrame]:
        symbol = instrument.mexc_symbol
        if not symbol:
            return None

        interval = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("mexc", "1d")
        url = "https://api.mexc.com/api/v3/klines"

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 1000,
        }
        if start:
            params["startTime"] = int(pd.to_datetime(start, utc=True).timestamp() * 1000)
        if end:
            params["endTime"] = int(pd.to_datetime(end, utc=True).timestamp() * 1000)

        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            return None

        raw = resp.json()
        if not isinstance(raw, list) or len(raw) == 0:
            return None

        records = []
        for row in raw:
            try:
                ts = pd.to_datetime(int(row[0]), unit="ms", utc=True)
                records.append({
                    "timestamp": ts,
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                })
            except (ValueError, IndexError):
                continue

        if not records:
            return None

        return pd.DataFrame(records).set_index("timestamp")

    def _fetch_coinbase(
        self,
        instrument: Instrument,
        timeframe: str,
        start: Optional[str],
        end: Optional[str],
    ) -> Optional[pd.DataFrame]:
        product = instrument.coinbase_product
        if not product:
            return None

        granularity = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("coinbase", 86400)
        url = f"https://api.exchange.coinbase.com/products/{product}/candles"

        params = {"granularity": granularity}
        if start:
            params["start"] = pd.to_datetime(start, utc=True).isoformat()
        if end:
            params["end"] = pd.to_datetime(end, utc=True).isoformat()

        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            return None

        raw = resp.json()
        if not isinstance(raw, list) or len(raw) == 0:
            return None

        records = []
        for row in raw:
            try:
                ts = pd.to_datetime(int(row[0]), unit="s", utc=True)
                records.append({
                    "timestamp": ts,
                    "open": float(row[3]),
                    "high": float(row[2]),
                    "low": float(row[1]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                })
            except (ValueError, IndexError):
                continue

        if not records:
            return None

        return pd.DataFrame(records).set_index("timestamp")
