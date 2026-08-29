"""Parquet-based persistent storage and cache manager for market data."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import List, Optional, Tuple
import pandas as pd

from marketdata.config import DATA_DIR


@dataclass
class CacheInfo:
    symbol: str
    category: str
    timeframe: str
    start: pd.Timestamp
    end: pd.Timestamp
    row_count: int
    file_size_bytes: int
    file_path: Path


class StorageManager:
    """Manages reading, writing, merging, and inspecting Parquet cache files."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, symbol: str, category: str, timeframe: str) -> Path:
        cat_dir = self.data_dir / category.lower()
        cat_dir.mkdir(parents=True, exist_ok=True)
        clean_symbol = symbol.replace("/", "_").replace(":", "_").upper()
        return cat_dir / f"{clean_symbol}_{timeframe.lower()}.parquet"

    def exists(self, symbol: str, category: str, timeframe: str) -> bool:
        path = self._get_file_path(symbol, category, timeframe)
        return path.exists() and path.stat().st_size > 0

    def load(
        self,
        symbol: str,
        category: str,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        path = self._get_file_path(symbol, category, timeframe)
        if not path.exists() or path.stat().st_size == 0:
            return None

        try:
            df = pd.read_parquet(path)
            if not isinstance(df.index, pd.DatetimeIndex):
                if "timestamp" in df.columns:
                    df = df.set_index("timestamp")
                df.index = pd.to_datetime(df.index, utc=True)
            elif df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

            if start:
                start_ts = pd.to_datetime(start, utc=True)
                df = df[df.index >= start_ts]
            if end:
                end_ts = pd.to_datetime(end, utc=True)
                df = df[df.index <= end_ts]

            return df
        except Exception:
            return None

    def save(self, symbol: str, category: str, timeframe: str, df: pd.DataFrame) -> Path:
        """Saves dataframe atomically using temporary file to prevent corruption."""
        path = self._get_file_path(symbol, category, timeframe)
        if df.empty:
            return path

        clean_df = df[~df.index.duplicated(keep="last")].sort_index()
        tmp_path = path.with_suffix(f".tmp.{os.getpid()}")
        clean_df.to_parquet(tmp_path, engine="pyarrow", compression="snappy")
        
        # Atomic replace
        if path.exists():
            path.unlink()
        tmp_path.rename(path)
        return path

    def merge_and_save(
        self,
        symbol: str,
        category: str,
        timeframe: str,
        new_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if new_df.empty:
            existing = self.load(symbol, category, timeframe)
            return existing if existing is not None else new_df

        existing_df = self.load(symbol, category, timeframe)
        if existing_df is None or existing_df.empty:
            merged = new_df
        else:
            combined = pd.concat([existing_df, new_df])
            merged = combined[~combined.index.duplicated(keep="last")].sort_index()

        self.save(symbol, category, timeframe, merged)
        return merged

    def get_cached_range(
        self, symbol: str, category: str, timeframe: str
    ) -> Optional[Tuple[pd.Timestamp, pd.Timestamp, int]]:
        df = self.load(symbol, category, timeframe)
        if df is None or df.empty:
            return None
        return df.index.min(), df.index.max(), len(df)

    def get_last_timestamp(self, symbol: str, category: str, timeframe: str) -> Optional[pd.Timestamp]:
        """Fast lookup of latest timestamp recorded in the cache."""
        cached_range = self.get_cached_range(symbol, category, timeframe)
        if cached_range:
            return cached_range[1]
        return None

    def list_cached_info(self) -> List[CacheInfo]:
        results = []
        for p in self.data_dir.rglob("*.parquet"):
            try:
                cat = p.parent.name
                stem = p.stem
                if "_" not in stem:
                    continue
                parts = stem.rsplit("_", 1)
                sym, tf = parts[0], parts[1]
                
                df = pd.read_parquet(p)
                if df.empty:
                    continue
                
                idx = pd.to_datetime(df.index if isinstance(df.index, pd.DatetimeIndex) else df["timestamp"], utc=True)
                results.append(
                    CacheInfo(
                        symbol=sym,
                        category=cat,
                        timeframe=tf,
                        start=idx.min(),
                        end=idx.max(),
                        row_count=len(df),
                        file_size_bytes=p.stat().st_size,
                        file_path=p,
                    )
                )
            except Exception:
                continue
        return results
