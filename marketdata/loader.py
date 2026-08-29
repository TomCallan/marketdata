"""On-Demand Data Loader and Orchestration Engine."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import Dict, List, Optional
import pandas as pd

from marketdata.config import DATA_DIR, INFO_FILE
from marketdata.fetchers.base import get_fetchers_for_category, list_registered_fetchers
# Ensure all fetcher plugins are imported and registered
import marketdata.fetchers  # noqa: F401
from marketdata.registry import Instrument, InstrumentRegistry, get_registry
from marketdata.storage import CacheInfo, StorageManager

logger = logging.getLogger(__name__)


class DataLoader:
    """Orchestrates on-demand historical market data retrieval, caching, and synchronization."""

    def __init__(self, registry: Optional[InstrumentRegistry] = None, storage: Optional[StorageManager] = None):
        self.registry = registry or get_registry(INFO_FILE)
        self.storage = storage or StorageManager(DATA_DIR)

    def get(
        self,
        symbol: str,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data for an instrument on demand.

        1. Checks local Parquet cache.
        2. If fully cached for requested range, returns immediately.
        3. If missing or partially cached, iterates registered fetchers for this asset category,
           fetches data, merges into cache, and returns result.
        """
        inst = self.registry.get(symbol)
        if not inst:
            raise ValueError(f"Unknown symbol '{symbol}'. Symbol not found in registry.")

        tf = timeframe.lower()

        if not force_refresh:
            cached_range = self.storage.get_cached_range(inst.symbol, inst.category, tf)
            if cached_range:
                cached_min, cached_max, _ = cached_range
                
                req_start = pd.to_datetime(start, utc=True) if start else None
                req_end = pd.to_datetime(end, utc=True) if end else None

                start_covered = (req_start is None) or (cached_min <= req_start)
                end_covered = (req_end is None) or (cached_max >= req_end)

                if start_covered and end_covered:
                    df = self.storage.load(inst.symbol, inst.category, tf, start=start, end=end)
                    if df is not None and not df.empty:
                        return df

        new_data = self._fetch_from_providers(inst, tf, start=start, end=end)
        if new_data.empty and not force_refresh:
            cached_df = self.storage.load(inst.symbol, inst.category, tf, start=start, end=end)
            if cached_df is not None:
                return cached_df
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        merged_df = self.storage.merge_and_save(inst.symbol, inst.category, tf, new_data)

        if start:
            merged_df = merged_df[merged_df.index >= pd.to_datetime(start, utc=True)]
        if end:
            merged_df = merged_df[merged_df.index <= pd.to_datetime(end, utc=True)]

        return merged_df

    def _fetch_from_providers(
        self,
        instrument: Instrument,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Route to registered fetchers supporting this instrument category in priority order."""
        fetchers = get_fetchers_for_category(instrument.category)
        if not fetchers:
            logger.warning(f"No fetchers registered for category '{instrument.category}'")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        for fetcher in fetchers:
            try:
                df = fetcher.fetch(instrument, timeframe, start, end)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"Fetcher '{fetcher.name}' failed for {instrument.symbol}: {e}")
                continue

        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def download_all(
        self,
        category: Optional[str] = None,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        max_workers: int = 5,
    ) -> Dict[str, bool]:
        instruments = self.registry.list_all(category)
        results = {}

        def _fetch_one(inst: Instrument):
            try:
                df = self.get(inst.symbol, timeframe=timeframe, start=start, end=end, force_refresh=True)
                return inst.symbol, not df.empty, len(df)
            except Exception as e:
                logger.error(f"Error downloading {inst.symbol}: {e}")
                return inst.symbol, False, 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {executor.submit(_fetch_one, inst): inst.symbol for inst in instruments}
            for future in as_completed(future_to_sym):
                sym, success, count = future.result()
                results[sym] = success

        return results

    def get_cache_status(self) -> List[CacheInfo]:
        return self.storage.list_cached_info()

    @staticmethod
    def list_sources() -> Dict[str, dict]:
        return list_registered_fetchers()


_default_loader: Optional[DataLoader] = None

def get_historical_data(
    symbol: str,
    timeframe: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    On-demand helper function to get historical OHLCV data.

    Example:
        >>> df = get_historical_data('BTCUSD', timeframe='1h', start='2024-01-01')
        >>> df_aapl = get_historical_data('AAPL', timeframe='1d')
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = DataLoader()
    return _default_loader.get(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        force_refresh=force_refresh,
    )
