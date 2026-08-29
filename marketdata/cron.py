"""Server Cron Sync Engine, Market Hours Filtering, and Daemon Scheduler."""

from dataclasses import dataclass, field
import datetime
import logging
from pathlib import Path
import time
from typing import Dict, List, Optional
import pandas as pd

from marketdata.config import BASE_DIR, LOGS_DIR
from marketdata.loader import DataLoader
from marketdata.registry import Instrument, get_registry
from marketdata.storage import StorageManager

logger = logging.getLogger("marketdata.cron")

# Setup file logging for cron jobs
CRON_LOG_FILE = LOGS_DIR / "cron_sync.log"


@dataclass
class SyncResult:
    symbol: str
    category: str
    timeframe: str
    status: str  # 'updated', 'skipped_closed', 'up_to_date', 'error', 'no_data'
    bars_added: int = 0
    message: str = ""


@dataclass
class SyncReport:
    timestamp: pd.Timestamp = field(default_factory=lambda: pd.Timestamp.now(tz="UTC"))
    duration_seconds: float = 0.0
    total_series: int = 0
    updated_count: int = 0
    skipped_closed_count: int = 0
    up_to_date_count: int = 0
    error_count: int = 0
    total_bars_added: int = 0
    results: List[SyncResult] = field(default_factory=list)


def is_market_open(instrument: Instrument, now_utc: Optional[pd.Timestamp] = None) -> bool:
    """
    Determines if the market for an instrument is actively open at current UTC time.
    """
    if now_utc is None:
        now_utc = pd.Timestamp.now(tz="UTC")

    cat = instrument.category.lower()

    # Crypto is 24/7/365
    if cat == "crypto":
        return True

    weekday = now_utc.weekday()  # Monday=0, Sunday=6
    hour = now_utc.hour
    minute = now_utc.minute

    # Forex: 24/5 from Sunday 21:05 UTC to Friday 20:55 UTC
    if cat == "forex":
        if weekday == 5:  # Saturday -> closed
            return False
        if weekday == 6:  # Sunday -> open after 21:05
            return (hour > 21) or (hour == 21 and minute >= 5)
        if weekday == 4:  # Friday -> open before 20:55
            return (hour < 20) or (hour == 20 and minute <= 55)
        return True  # Mon-Thu -> open 24h

    # Stocks, Indices, Commodities: Mon-Fri
    if weekday in [5, 6]:  # Weekend
        return False

    return True


class CronSyncEngine:
    """High-efficiency incremental delta synchronization engine for server cron jobs."""

    def __init__(self, loader: Optional[DataLoader] = None, storage: Optional[StorageManager] = None):
        self.loader = loader or DataLoader()
        self.storage = storage or self.loader.storage
        self.registry = self.loader.registry

    def _calculate_delta_start(
        self,
        last_ts: pd.Timestamp,
        timeframe: str,
        overlap_bars: int = 2,
    ) -> str:
        """Calculate start timestamp overlapping N bars to ensure candle finalization."""
        tf_lower = timeframe.lower()
        if tf_lower == "1m":
            delta = pd.Timedelta(minutes=overlap_bars)
        elif tf_lower == "5m":
            delta = pd.Timedelta(minutes=5 * overlap_bars)
        elif tf_lower == "15m":
            delta = pd.Timedelta(minutes=15 * overlap_bars)
        elif tf_lower == "30m":
            delta = pd.Timedelta(minutes=30 * overlap_bars)
        elif tf_lower == "1h":
            delta = pd.Timedelta(hours=overlap_bars)
        elif tf_lower == "4h":
            delta = pd.Timedelta(hours=4 * overlap_bars)
        elif tf_lower == "1d":
            delta = pd.Timedelta(days=overlap_bars)
        else:
            delta = pd.Timedelta(days=overlap_bars)

        start_dt = last_ts - delta
        if tf_lower == "1d":
            return start_dt.strftime("%Y-%m-%d")
        return start_dt.strftime("%Y-%m-%d %H:%M:%S")

    def sync(
        self,
        categories: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        overlap_bars: int = 2,
        check_market_hours: bool = True,
        force: bool = False,
    ) -> SyncReport:
        """
        Execute smart incremental sync for specified categories and timeframes.
        """
        start_time = time.time()
        now_utc = pd.Timestamp.now(tz="UTC")

        if timeframes is None:
            timeframes = ["1d"]

        instruments = []
        if categories:
            for cat in categories:
                instruments.extend(self.registry.list_all(cat))
        else:
            instruments = self.registry.list_all()

        report = SyncReport(
            timestamp=now_utc,
            total_series=len(instruments) * len(timeframes),
        )

        for tf in timeframes:
            for inst in instruments:
                # 1. Market hours check
                if check_market_hours and not force and not is_market_open(inst, now_utc):
                    report.skipped_closed_count += 1
                    report.results.append(
                        SyncResult(
                            symbol=inst.symbol,
                            category=inst.category,
                            timeframe=tf,
                            status="skipped_closed",
                            message="Market closed",
                        )
                    )
                    continue

                # 2. Inspect existing cache
                cached_range = self.storage.get_cached_range(inst.symbol, inst.category, tf)
                start_str = None
                initial_count = 0

                if cached_range:
                    initial_count = cached_range[2]
                    last_ts = cached_range[1]
                    start_str = self._calculate_delta_start(last_ts, tf, overlap_bars)

                try:
                    df = self.loader.get(
                        symbol=inst.symbol,
                        timeframe=tf,
                        start=start_str,
                        force_refresh=True,
                    )
                    if df.empty:
                        report.results.append(
                            SyncResult(
                                symbol=inst.symbol,
                                category=inst.category,
                                timeframe=tf,
                                status="no_data",
                                message="No new bars retrieved",
                            )
                        )
                    else:
                        new_count = len(df)
                        added = max(0, new_count - initial_count)
                        report.total_bars_added += added
                        report.updated_count += 1
                        report.results.append(
                            SyncResult(
                                symbol=inst.symbol,
                                category=inst.category,
                                timeframe=tf,
                                status="updated",
                                bars_added=added,
                                message=f"Total: {new_count} bars",
                            )
                        )
                except Exception as e:
                    report.error_count += 1
                    report.results.append(
                        SyncResult(
                            symbol=inst.symbol,
                            category=inst.category,
                            timeframe=tf,
                            status="error",
                            message=str(e),
                        )
                    )

        report.duration_seconds = time.time() - start_time
        self._write_log(report)
        return report

    def _write_log(self, report: SyncReport) -> None:
        """Appends formatted sync summary to logs/cron_sync.log."""
        try:
            log_line = (
                f"[{report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}] "
                f"SYNC COMPLETED: {report.updated_count} updated, "
                f"{report.skipped_closed_count} closed/skipped, "
                f"{report.error_count} errors | "
                f"{report.total_bars_added} bars added in {report.duration_seconds:.2f}s\n"
            )
            with open(CRON_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception:
            pass


def generate_crontab_entries(python_path: str = "python", script_dir: Optional[Path] = None) -> str:
    """Generates standard Crontab configuration lines."""
    workdir = str(script_dir or BASE_DIR)
    return (
        "# ====================================================================\n"
        "# MarketData Automated Server Cron Schedules\n"
        "# ====================================================================\n"
        "# 1. Daily Sync at 00:05 UTC for all asset classes (1d timeframe)\n"
        f"5 0 * * * cd {workdir} && {python_path} -m marketdata.data sync --timeframe 1d >> {workdir}/logs/cron_sync.log 2>&1\n\n"
        "# 2. Hourly Sync at minute 2 for active markets (1h timeframe)\n"
        f"2 * * * * cd {workdir} && {python_path} -m marketdata.data sync --timeframe 1h >> {workdir}/logs/cron_sync.log 2>&1\n\n"
        "# 3. 15-Minute Sync for Crypto & Forex during active sessions\n"
        f"*/15 * * * * cd {workdir} && {python_path} -m marketdata.data sync --category crypto --category forex --timeframe 15m >> {workdir}/logs/cron_sync.log 2>&1\n"
    )


def generate_systemd_service(python_path: str = "python", script_dir: Optional[Path] = None) -> str:
    workdir = str(script_dir or BASE_DIR)
    return f"""[Unit]
Description=MarketData Hourly Incremental Sync Service
After=network.target

[Service]
Type=oneshot
WorkingDirectory={workdir}
ExecStart={python_path} -m marketdata.data sync --timeframe 1h
StandardOutput=append:{workdir}/logs/cron_sync.log
StandardError=append:{workdir}/logs/cron_sync.log

[Install]
WantedBy=multi-user.target
"""


def generate_systemd_timer() -> str:
    return """[Unit]
Description=Run MarketData Hourly Incremental Sync Timer

[Timer]
OnCalendar=*-*-* *:02:00
Persistent=true

[Install]
WantedBy=timers.target
"""
