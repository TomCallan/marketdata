"""Finnhub Market Data Fetcher."""

import logging
from typing import Optional
import pandas as pd
import requests

from marketdata.config import TIMEFRAME_MAPPINGS, get_api_key
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="finnhub",
    supported_categories=["stocks", "forex", "crypto", "indices"],
    priority=40,
)
class FinnhubFetcher(BaseFetcher):
    """Fetches market data from Finnhub REST API."""

    BASE_URL = "https://finnhub.io/api/v1"

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        api_key = get_api_key("finnhub")
        if not api_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        cat = instrument.category
        sym = instrument.symbol.upper()
        res = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("finnhub", "D")

        from_ts = int(pd.to_datetime(start, utc=True).timestamp()) if start else int(pd.Timestamp.now(tz="UTC").timestamp() - 365 * 86400)
        to_ts = int(pd.to_datetime(end, utc=True).timestamp()) if end else int(pd.Timestamp.now(tz="UTC").timestamp())

        endpoint = "/stock/candle"
        finnhub_symbol = sym

        if cat == "crypto":
            endpoint = "/crypto/candle"
            coin = sym.replace("USD", "").replace("USDT", "")
            finnhub_symbol = f"BINANCE:{coin}USDT"
        elif cat == "forex":
            endpoint = "/forex/candle"
            finnhub_symbol = f"OANDA:{sym[:3]}_{sym[3:]}" if len(sym) == 6 else f"OANDA:{sym}"

        url = f"{self.BASE_URL}{endpoint}"
        params = {
            "symbol": finnhub_symbol,
            "resolution": res,
            "from": from_ts,
            "to": to_ts,
            "token": api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get("s") != "ok" or not data.get("t"):
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            df = pd.DataFrame({
                "timestamp": pd.to_datetime(data["t"], unit="s", utc=True),
                "open": data["o"],
                "high": data["h"],
                "low": data["l"],
                "close": data["c"],
                "volume": data["v"],
            }).set_index("timestamp")

            return self.standardize_dataframe(df)

        except Exception as e:
            logger.warning(f"Finnhub request failed for {sym}: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
