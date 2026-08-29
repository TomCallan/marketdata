"""Massive (formerly Polygon.io) Market Data Fetcher."""

import logging
from typing import Optional
import pandas as pd
import requests

from marketdata.config import TIMEFRAME_MAPPINGS, get_api_key
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="massive",
    supported_categories=["stocks", "indices", "forex", "crypto"],
    priority=25,
)
class MassiveFetcher(BaseFetcher):
    """Fetches historical aggregates from Massive / Polygon.io REST API."""

    BASE_URLS = [
        "https://api.massive.com/v2/aggs/ticker",
        "https://api.polygon.io/v2/aggs/ticker",
    ]

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        api_key = get_api_key("massive") or get_api_key("polygon")
        if not api_key:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        cat = instrument.category
        sym = instrument.symbol.upper()

        polygon_tf = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("polygon", "1/day")
        multiplier, timespan = polygon_tf.split("/")

        # Convert symbol to Massive/Polygon format
        if cat == "crypto":
            coin = sym.replace("USD", "").replace("USDT", "")
            poly_ticker = f"X:{coin}USD"
        elif cat == "forex":
            poly_ticker = f"C:{sym[:3]}{sym[3:]}" if len(sym) == 6 else f"C:{sym}"
        else:
            poly_ticker = sym.replace("-", ".")

        from_date = pd.to_datetime(start, utc=True).strftime("%Y-%m-%d") if start else (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=730)).strftime("%Y-%m-%d")
        to_date = pd.to_datetime(end, utc=True).strftime("%Y-%m-%d") if end else pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")

        for base_url in self.BASE_URLS:
            url = f"{base_url}/{poly_ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
            params = {
                "adjusted": "true",
                "sort": "asc",
                "limit": 50000,
                "apiKey": api_key,
            }

            try:
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if not data.get("results"):
                    continue

                records = []
                for row in data["results"]:
                    records.append({
                        "timestamp": pd.to_datetime(row["t"], unit="ms", utc=True),
                        "open": float(row["o"]),
                        "high": float(row["h"]),
                        "low": float(row["l"]),
                        "close": float(row["c"]),
                        "volume": float(row.get("v", 0.0)),
                    })

                df = pd.DataFrame(records).set_index("timestamp")
                return self.standardize_dataframe(df)

            except Exception as e:
                logger.debug(f"Massive/Polygon request failed for {sym} at {base_url}: {e}")
                continue

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


PolygonFetcher = MassiveFetcher
