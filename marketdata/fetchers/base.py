"""Base class and extensible plugin registry for market data fetchers."""

from abc import ABC, abstractmethod
import logging
from typing import Callable, Dict, List, Optional, Type
import pandas as pd

from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    """Abstract base class for all market data fetchers."""

    name: str = "base"
    supported_categories: List[str] = []
    priority: int = 100

    @abstractmethod
    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data for an instrument."""
        pass

    @staticmethod
    def standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure standard column names, UTC DatetimeIndex, and correct types."""
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = df.copy()
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.columns = [str(c).strip().lower() for c in df.columns]

        required = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Fetched dataframe missing expected columns: {missing}")

        df = df[required]

        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" in df.columns or "date" in df.columns:
                t_col = "timestamp" if "timestamp" in df.columns else "date"
                df.index = pd.to_datetime(df[t_col], utc=True)
                df = df.drop(columns=[t_col])
            else:
                df.index = pd.to_datetime(df.index, utc=True)
        else:
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

        df.index.name = "timestamp"

        for col in required:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close"])
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()

        return df


_FETCHERS: Dict[str, BaseFetcher] = {}
_FETCHER_CLASSES: Dict[str, Type[BaseFetcher]] = {}


def register_fetcher(
    name: Optional[str] = None,
    supported_categories: Optional[List[str]] = None,
    priority: int = 100,
) -> Callable[[Type[BaseFetcher]], Type[BaseFetcher]]:
    """Decorator to register a new data source fetcher plugin."""
    def decorator(cls: Type[BaseFetcher]) -> Type[BaseFetcher]:
        fetcher_name = name or getattr(cls, "name", cls.__name__.lower())
        cls.name = fetcher_name
        if supported_categories is not None:
            cls.supported_categories = supported_categories
        cls.priority = priority

        _FETCHER_CLASSES[fetcher_name] = cls
        _FETCHERS[fetcher_name] = cls()
        logger.info(f"Registered market data fetcher: '{fetcher_name}' (priority={priority})")
        return cls

    return decorator


def get_fetcher(name: str) -> Optional[BaseFetcher]:
    """Retrieve a registered fetcher instance by name."""
    if name not in _FETCHERS and name in _FETCHER_CLASSES:
        _FETCHERS[name] = _FETCHER_CLASSES[name]()
    return _FETCHERS.get(name)


def get_fetchers_for_category(category: str) -> List[BaseFetcher]:
    """Retrieve all registered fetchers supporting the given category sorted by priority."""
    cat_lower = category.lower()
    matching = []
    for name, fetcher in _FETCHERS.items():
        if not fetcher.supported_categories or cat_lower in [c.lower() for c in fetcher.supported_categories]:
            matching.append(fetcher)
    
    matching.sort(key=lambda f: f.priority)
    return matching


def list_registered_fetchers() -> Dict[str, dict]:
    """List all registered fetchers and their configuration."""
    return {
        name: {
            "class": f.__class__.__name__,
            "priority": f.priority,
            "supported_categories": f.supported_categories,
        }
        for name, f in _FETCHERS.items()
    }
