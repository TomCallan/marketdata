"""Automated test suite for MarketData pipeline."""

import shutil
import tempfile
from pathlib import Path
import pandas as pd
import unittest

from marketdata.config import INFO_FILE
from marketdata.fetchers.crypto_fetcher import CryptoPublicFetcher
from marketdata.fetchers.yfinance_fetcher import YahooFinanceFetcher
from marketdata.loader import DataLoader, get_historical_data
from marketdata.registry import InstrumentRegistry, get_registry
from marketdata.storage import StorageManager


def test_registry_parsing():
    """Verify info.md parses all instruments across 5 categories."""
    reg = InstrumentRegistry(INFO_FILE)
    instruments = reg.list_all()
    assert len(instruments) >= 230, f"Expected >= 230 instruments, got {len(instruments)}"

    categories = reg.categories
    assert len(categories["crypto"]) >= 100
    assert len(categories["stocks"]) >= 70
    assert len(categories["commodities"]) >= 7
    assert len(categories["indices"]) >= 7
    assert len(categories["forex"]) >= 35

    btc = reg.get("BTCUSD")
    assert btc is not None
    assert btc.category == "crypto"
    assert btc.max_leverage_long == "6x"

    eurusd = reg.get("EURUSD")
    assert eurusd is not None
    assert eurusd.category == "forex"
    assert eurusd.commission == "0.01% of notional"
    assert eurusd.yfinance_ticker == "EURUSD=X"

    cl = reg.get("CL")
    assert cl is not None
    assert cl.category == "commodities"
    assert cl.yfinance_ticker == "CL=F"


def test_storage_parquet_roundtrip():
    """Test Parquet caching, reading, and incremental merging."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = StorageManager(Path(tmp_dir))

        dates = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
        df1 = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [105.0, 106.0, 107.0, 108.0, 109.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [104.0, 105.0, 106.0, 107.0, 108.0],
                "volume": [1000.0, 1100.0, 1200.0, 1300.0, 1400.0],
            },
            index=dates,
        )
        df1.index.name = "timestamp"

        storage.save("TEST", "stocks", "1d", df1)
        assert storage.exists("TEST", "stocks", "1d")

        loaded = storage.load("TEST", "stocks", "1d")
        assert len(loaded) == 5
        assert (loaded["close"] == df1["close"]).all()

        dates2 = pd.date_range("2024-01-04", periods=4, freq="D", tz="UTC")
        df2 = pd.DataFrame(
            {
                "open": [103.5, 104.5, 105.5, 106.5],
                "high": [108.5, 109.5, 110.5, 111.5],
                "low": [102.5, 103.5, 104.5, 105.5],
                "close": [107.5, 108.5, 109.5, 110.5],
                "volume": [1350.0, 1450.0, 1550.0, 1650.0],
            },
            index=dates2,
        )
        df2.index.name = "timestamp"

        merged = storage.merge_and_save("TEST", "stocks", "1d", df2)
        assert len(merged) == 7
        assert merged.index.min() == pd.to_datetime("2024-01-01", utc=True)
        assert merged.index.max() == pd.to_datetime("2024-01-07", utc=True)


def test_yfinance_fetcher_live():
    """Verify live fetch for Stock, Forex, Commodity, Index."""
    fetcher = YahooFinanceFetcher()
    reg = get_registry()

    aapl = reg.get("AAPL")
    df_aapl = fetcher.fetch(aapl, timeframe="1d", start="2024-01-01", end="2024-01-10")
    assert not df_aapl.empty
    assert "close" in df_aapl.columns
    assert isinstance(df_aapl.index, pd.DatetimeIndex)

    eur = reg.get("EURUSD")
    df_eur = fetcher.fetch(eur, timeframe="1d", start="2024-01-01", end="2024-01-10")
    assert not df_eur.empty


def test_crypto_fetcher_live():
    """Verify live fetch from public crypto APIs."""
    fetcher = CryptoPublicFetcher()
    reg = get_registry()

    btc = reg.get("BTCUSD")
    df_btc = fetcher.fetch(btc, timeframe="1d", start="2024-01-01", end="2024-01-10")
    assert not df_btc.empty

    grass = reg.get("GRASSUSD")
    if grass:
        df_grass = fetcher.fetch(grass, timeframe="1d")
        assert not df_grass.empty


def test_dataloader_end_to_end():
    """Test DataLoader caching and on-demand retrieval."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = StorageManager(Path(tmp_dir))
        loader = DataLoader(storage=storage)

        df1 = loader.get("AAPL", timeframe="1d", start="2024-01-01", end="2024-01-10")
        assert not df1.empty
        assert storage.exists("AAPL", "stocks", "1d")

        df2 = loader.get("AAPL", timeframe="1d", start="2024-01-01", end="2024-01-10")
        assert len(df1) == len(df2)


def test_ticker_converter():
    """Verify bidirectional ticker conversion across providers and Python object model."""
    from marketdata.mappings import TickerConversionTable, TickerMapping, load_ticker_conversions

    table = load_ticker_conversions()
    assert len(table) >= 230

    btc = table["BTCUSD"]
    assert isinstance(btc, TickerMapping)
    assert btc.symbol == "BTCUSD"
    assert btc.category == "crypto"
    assert btc.yfinance == "BTC-USD"
    assert btc.gateio == "BTC_USDT"
    assert btc.mexc == "BTCUSDT"
    assert btc.coinbase == "BTC-USD"
    assert btc.get_provider_ticker("yfinance") == "BTC-USD"

    forex_mappings = table.by_category("forex")
    assert len(forex_mappings) >= 35
    assert all(m.category == "forex" for m in forex_mappings)

    df_table = table.to_dataframe()
    assert len(df_table) == len(table)
    assert "yfinance" in df_table.columns
    assert "gateio" in df_table.columns

    assert table.to_provider("BTCUSD", "yfinance") == "BTC-USD"
    assert table.to_provider("BTCUSD", "gateio") == "BTC_USDT"
    assert table.to_provider("BTCUSD", "mexc") == "BTCUSDT"
    assert table.to_provider("BTCUSD", "coinbase") == "BTC-USD"

    assert table.to_provider("EURUSD", "yfinance") == "EURUSD=X"
    assert table.to_provider("CL", "yfinance") == "CL=F"
    assert table.to_provider("BRKB", "yfinance") == "BRK-B"

    assert table.from_provider("BTC-USD", "yfinance") == "BTCUSD"
    assert table.from_provider("EURUSD=X", "yfinance") == "EURUSD"
    assert table.from_provider("CL=F", "yfinance") == "CL"


def test_custom_fetcher_plugin():
    """Verify new data source fetchers can be registered dynamically."""
    from marketdata.fetchers.base import BaseFetcher, register_fetcher, get_fetchers_for_category, _FETCHERS

    @register_fetcher(name="test_dummy_plugin", supported_categories=["commodities"], priority=1)
    class DummyCommodityFetcher(BaseFetcher):
        def fetch(self, instrument, timeframe="1d", start=None, end=None):
            dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
            df = pd.DataFrame(
                {
                    "open": [1.0, 2.0, 3.0],
                    "high": [1.1, 2.1, 3.1],
                    "low": [0.9, 1.9, 2.9],
                    "close": [1.05, 2.05, 3.05],
                    "volume": [10.0, 20.0, 30.0],
                },
                index=dates,
            )
            df.index.name = "timestamp"
            return df

    matching = get_fetchers_for_category("commodities")
    assert any(f.name == "test_dummy_plugin" for f in matching)
    assert matching[0].name == "test_dummy_plugin"

    _FETCHERS.pop("test_dummy_plugin", None)


def test_ccxt_fetcher():
    """Verify CCXT multi-exchange crypto fetcher."""
    from marketdata.fetchers.ccxt_fetcher import CCXTFetcher

    fetcher = CCXTFetcher()
    reg = get_registry()
    btc = reg.get("BTCUSD")

    df = fetcher.fetch(btc, timeframe="1d", start="2024-01-01", end="2024-01-05")
    assert not df.empty
    assert "close" in df.columns
    assert len(df) >= 3


def test_api_key_fetchers_fallback():
    """Verify Alpha Vantage, Finnhub, and Tiingo handle absent API keys gracefully."""
    from marketdata.fetchers.alphavantage_fetcher import AlphaVantageFetcher
    from marketdata.fetchers.finnhub_fetcher import FinnhubFetcher
    from marketdata.fetchers.tiingo_fetcher import TiingoFetcher

    reg = get_registry()
    aapl = reg.get("AAPL")

    av = AlphaVantageFetcher()
    df_av = av.fetch(aapl, timeframe="1d")
    assert isinstance(df_av, pd.DataFrame)

    fh = FinnhubFetcher()
    df_fh = fh.fetch(aapl, timeframe="1d")
    assert isinstance(df_fh, pd.DataFrame)

    tg = TiingoFetcher()
    df_tg = tg.fetch(aapl, timeframe="1d")
    assert isinstance(df_tg, pd.DataFrame)


def test_market_hours_checker():
    """Verify market hours detection for crypto, forex, and equities."""
    from marketdata.cron import is_market_open
    reg = get_registry()

    btc = reg.get("BTCUSD")
    eur = reg.get("EURUSD")
    aapl = reg.get("AAPL")

    # Sunday noon UTC: Crypto is open, Forex/Stocks closed
    sunday_noon = pd.Timestamp("2024-01-07 12:00:00", tz="UTC")
    assert is_market_open(btc, sunday_noon) is True
    assert is_market_open(eur, sunday_noon) is False
    assert is_market_open(aapl, sunday_noon) is False

    # Tuesday 14:00 UTC: All open
    tuesday_afternoon = pd.Timestamp("2024-01-09 14:00:00", tz="UTC")
    assert is_market_open(btc, tuesday_afternoon) is True
    assert is_market_open(eur, tuesday_afternoon) is True
    assert is_market_open(aapl, tuesday_afternoon) is True


def test_massive_and_twelvedata_fetchers():
    """Verify Massive (Polygon) and Twelve Data fetchers."""
    from marketdata.fetchers.polygon_fetcher import MassiveFetcher
    from marketdata.fetchers.twelvedata_fetcher import TwelveDataFetcher

    reg = get_registry()
    aapl = reg.get("AAPL")

    poly = MassiveFetcher()
    df_p = poly.fetch(aapl, timeframe="1d")
    assert isinstance(df_p, pd.DataFrame)

    td = TwelveDataFetcher()
    df_td = td.fetch(aapl, timeframe="1d")
    assert isinstance(df_td, pd.DataFrame)


def test_cron_delta_sync():
    """Verify CronSyncEngine delta-sync execution."""
    from marketdata.cron import CronSyncEngine

    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = StorageManager(Path(tmp_dir))
        loader = DataLoader(storage=storage)
        engine = CronSyncEngine(loader=loader, storage=storage)

        # Initial sync for BTCUSD
        report = engine.sync(categories=["crypto"], timeframes=["1d"], force=True)
        assert report.total_series >= 100
        assert report.error_count == 0
