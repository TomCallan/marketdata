"""Yahoo Finance Fetcher for Stocks, Forex, Commodities, Indices, and Crypto."""

import logging
from typing import Optional
import pandas as pd
import yfinance as yf

from marketdata.config import TIMEFRAME_MAPPINGS
from marketdata.fetchers.base import BaseFetcher, register_fetcher
from marketdata.registry import Instrument

logger = logging.getLogger(__name__)


@register_fetcher(
    name="yfinance",
    supported_categories=["stocks", "forex", "commodities", "indices", "crypto"],
    priority=20,
)
class YahooFinanceFetcher(BaseFetcher):
    """Fetches market data from Yahoo Finance via yfinance."""

    def fetch(
        self,
        instrument: Instrument,
        timeframe: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        ticker_symbol = instrument.yfinance_ticker or instrument.symbol
        yf_interval = TIMEFRAME_MAPPINGS.get(timeframe, {}).get("yf", "1d")

        try:
            ticker = yf.Ticker(ticker_symbol)
            
            # Determine maximum allowable period for the timeframe
            max_period = "max"
            if yf_interval == "1h":
                max_period = "730d"
            elif yf_interval in ["30m", "15m", "5m"]:
                max_period = "60d"
            elif yf_interval == "1m":
                max_period = "7d"

            clean_start = None
            clean_end = None
            if start:
                if yf_interval == "1d":
                    clean_start = str(start)[:10]
                else:
                    clean_start = int(pd.to_datetime(start, utc=True).timestamp())

            if end:
                if yf_interval == "1d":
                    clean_end = str(end)[:10]
                else:
                    clean_end = int(pd.to_datetime(end, utc=True).timestamp())

            kwargs = {
                "interval": yf_interval,
                "auto_adjust": False,
            }
            if clean_start:
                kwargs["start"] = clean_start
            if clean_end:
                kwargs["end"] = clean_end
            if not clean_start and not clean_end:
                kwargs["period"] = max_period

            df = ticker.history(**kwargs)

            if df is None or df.empty:
                df = yf.download(
                    tickers=ticker_symbol,
                    interval=yf_interval,
                    start=clean_start,
                    end=clean_end,
                    period=max_period if (not clean_start and not clean_end) else None,
                    progress=False,
                    auto_adjust=False,
                )

            if df is None or df.empty:
                logger.warning(f"No data returned from Yahoo Finance for {ticker_symbol}")
                return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

            if isinstance(df.columns, pd.MultiIndex):
                if ticker_symbol in df.columns.levels[1]:
                    df = df.xs(ticker_symbol, axis=1, level=1)
                else:
                    df.columns = df.columns.get_level_values(0)

            keep_cols = [c for c in df.columns if str(c).lower() in ["open", "high", "low", "close", "volume"]]
            df = df[keep_cols]

            return self.standardize_dataframe(df)

        except Exception as e:
            logger.warning(f"Error fetching {ticker_symbol} from Yahoo Finance: {e}")
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
