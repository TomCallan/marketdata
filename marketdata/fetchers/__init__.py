"""Data fetchers package for MarketData toolkit."""

from marketdata.fetchers.base import (
    BaseFetcher,
    get_fetcher,
    get_fetchers_for_category,
    list_registered_fetchers,
    register_fetcher,
)
from marketdata.fetchers.alphavantage_fetcher import AlphaVantageFetcher
from marketdata.fetchers.ccxt_fetcher import CCXTFetcher
from marketdata.fetchers.crypto_fetcher import CryptoPublicFetcher
from marketdata.fetchers.finnhub_fetcher import FinnhubFetcher
from marketdata.fetchers.polygon_fetcher import PolygonFetcher
from marketdata.fetchers.tiingo_fetcher import TiingoFetcher
from marketdata.fetchers.twelvedata_fetcher import TwelveDataFetcher
from marketdata.fetchers.yfinance_fetcher import YahooFinanceFetcher

__all__ = [
    "BaseFetcher",
    "register_fetcher",
    "get_fetcher",
    "get_fetchers_for_category",
    "list_registered_fetchers",
    "YahooFinanceFetcher",
    "CryptoPublicFetcher",
    "CCXTFetcher",
    "PolygonFetcher",
    "TwelveDataFetcher",
    "TiingoFetcher",
    "FinnhubFetcher",
    "AlphaVantageFetcher",
]
