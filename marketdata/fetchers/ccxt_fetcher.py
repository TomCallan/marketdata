"""CCXT Multi-Exchange Crypto Fetcher."""

import logging
from typing import Dict, List, Optional
import pandas as pd

try:
    import ccxt
    HAS_CCXT = True
except ImportError:
    HAS_CCXT = False

from marketdata.config import TIMEFRAME_MAPPINGS
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="ccxt",
    supported_categories=["crypto"],
    priority=5,
)
class CCXTFetcher(BaseFetcher):
    """Fetches crypto OHLCV data using CCXT without API keys."""

    EXCHANGE_IDS = ["gate", "coinbase", "kraken", "bybit", "okx", "mexc"]

    def __init__(self):
        self._exchanges: Dict[str, ccxt.Exchange] = {}

    def _get_exchange(self, exchange_id: str) -> Optional[ccxt.Exchange]:
        if not HAS_CCXT:
            return None

        if exchange_id not in self._exchanges:
            try:
                exchange_class = getattr(ccxt, exchange_id)
                self._exchanges[exchange_id] = exchange_class({
                    "enableRateLimit": True,
                    "timeout": 15000,
                })
            except Exception as e:
                logger.warning(f"Failed to initialize CCXT exchange '{exchange_id}': {e}")
                return None

        return self._exchanges[exchange_id]

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        if not HAS_CCXT:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        tf = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("ccxt", "1d")
        sym = instrument.symbol.upper()

        if sym.endswith("USD") and len(sym) > 3:
            coin = sym[:-3]
        elif sym.endswith("USDT") and len(sym) > 4:
            coin = sym[:-4]
        else:
            coin = sym

        candidate_symbols = [
            f"{coin}/USDT",
            f"{coin}/USD",
            f"{coin}/USDC",
        ]

        since_ms = int(pd.to_datetime(start, utc=True).timestamp() * 1000) if start else None

        for ex_id in self.EXCHANGE_IDS:
            ex = self._get_exchange(ex_id)
            if not ex:
                continue

            for market_symbol in candidate_symbols:
                try:
                    ohlcv = ex.fetch_ohlcv(
                        symbol=market_symbol,
                        timeframe=tf,
                        since=since_ms,
                        limit=1000,
                    )
                    if ohlcv and len(ohlcv) > 0:
                        df = pd.DataFrame(
                            ohlcv,
                            columns=["timestamp", "open", "high", "low", "close", "volume"],
                        )
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                        df = df.set_index("timestamp")

                        if end:
                            df = df[df.index <= pd.to_datetime(end, utc=True)]

                        return self.standardize_dataframe(df)

                except Exception as e:
                    logger.debug(f"CCXT {ex_id} failed for {market_symbol}: {e}")
                    continue

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
