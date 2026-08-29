"""Rich-Powered Command Line Interface for MarketData Toolkit."""

import argparse
import sys
from typing import Optional
import pandas as pd

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from marketdata.loader import DataLoader
from marketdata.mappings import TickerConverter, generate_mappings_and_table
from marketdata.registry import get_registry

console = Console() if HAS_RICH else None


def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def cmd_list(args):
    reg = get_registry()
    instruments = reg.list_all(category=args.category)
    
    if not instruments:
        if HAS_RICH:
            console.print(f"[yellow]No instruments found for category '{args.category}'.[/yellow]")
        else:
            print(f"No instruments found for category '{args.category}'.")
        return

    if HAS_RICH:
        table = Table(
            title=f"Tradeable Instruments ({len(instruments)})",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("Symbol", style="bold white", width=14)
        table.add_column("Category", style="magenta", width=12)
        table.add_column("Max Lev (L/S)", style="green", width=14, justify="center")
        table.add_column("Commission", style="yellow", width=18)
        table.add_column("Trading Hours", style="cyan")

        for inst in instruments:
            lev = f"{inst.max_leverage_long}/{inst.max_leverage_short}"
            table.add_row(inst.symbol, inst.category.capitalize(), lev, inst.commission, inst.trading_hours)

        console.print(table)
    else:
        print(f"\nFound {len(instruments)} tradeable instrument(s):")
        print("-" * 90)
        print(f"{'Symbol':<14} {'Category':<12} {'Max Lev (L/S)':<15} {'Commission':<18} {'Trading Hours'}")
        print("-" * 90)
        for inst in instruments:
            lev = f"{inst.max_leverage_long}/{inst.max_leverage_short}"
            print(f"{inst.symbol:<14} {inst.category:<12} {lev:<15} {inst.commission:<18} {inst.trading_hours}")
        print("-" * 90)


def cmd_info(args):
    reg = get_registry()
    inst = reg.get(args.symbol)
    if not inst:
        if HAS_RICH:
            console.print(f"[bold red]Error:[/bold red] Symbol '{args.symbol}' not found in registry.")
        else:
            print(f"Error: Symbol '{args.symbol}' not found in registry.")
        sys.exit(1)

    if HAS_RICH:
        content = (
            f"[bold cyan]Category:[/bold cyan]         {inst.category.capitalize()}\n"
            f"[bold cyan]Max Leverage:[/bold cyan]     [green]Long: {inst.max_leverage_long}[/green] | [red]Short: {inst.max_leverage_short}[/red]\n"
            f"[bold cyan]Commission:[/bold cyan]       {inst.commission}\n"
            f"[bold cyan]Trading Hours:[/bold cyan]    {inst.trading_hours}\n"
            f"[bold cyan]Overnight Swap:[/bold cyan]   {inst.overnight_swap}\n"
            f"[bold cyan]Trading Size:[/bold cyan]     {inst.trading_size}\n\n"
            f"[bold magenta]External Provider Tickers:[/bold magenta]\n"
            f"  - [bold]Yahoo Finance:[/bold]  [yellow]{inst.yfinance_ticker or 'N/A'}[/yellow]\n"
            f"  - [bold]Gate.io Pair:[/bold]   [yellow]{inst.gateio_pair or 'N/A'}[/yellow]\n"
            f"  - [bold]MEXC Symbol:[/bold]    [yellow]{inst.mexc_symbol or 'N/A'}[/yellow]\n"
            f"  - [bold]Coinbase:[/bold]       [yellow]{inst.coinbase_product or 'N/A'}[/yellow]"
        )
        panel = Panel(
            content,
            title=f"[bold white on blue] Instrument Specification: {inst.symbol} [/bold white on blue]",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=False,
        )
        console.print(panel)
    else:
        print(f"\nInstrument: {inst.symbol}")
        print("=" * 50)
        print(f"Category:         {inst.category}")
        print(f"Max Leverage:     Long: {inst.max_leverage_long} | Short: {inst.max_leverage_short}")
        print(f"Commission:       {inst.commission}")
        print(f"Trading Hours:    {inst.trading_hours}")
        print(f"Overnight Swap:   {inst.overnight_swap}")
        print(f"Trading Size:     {inst.trading_size}")
        print("\nResolved Provider Tickers:")
        print(f"  Yahoo Finance:  {inst.yfinance_ticker or 'N/A'}")
        print(f"  Gate.io Pair:   {inst.gateio_pair or 'N/A'}")
        print(f"  MEXC Symbol:    {inst.mexc_symbol or 'N/A'}")
        print(f"  Coinbase:       {inst.coinbase_product or 'N/A'}")
        print("=" * 50)


def cmd_convert(args):
    conv = TickerConverter()
    if args.reverse:
        res = conv.from_provider(args.symbol, provider=args.provider)
        if HAS_RICH:
            console.print(f"Provider [bold cyan]{args.provider}[/bold cyan] ticker '[bold yellow]{args.symbol}[/bold yellow]' -> Internal symbol: '[bold green]{res}[/bold green]'")
        else:
            print(f"Provider '{args.provider}' ticker '{args.symbol}' -> Internal symbol: '{res}'")
    else:
        res = conv.to_provider(args.symbol, provider=args.provider)
        if HAS_RICH:
            console.print(f"Internal symbol '[bold green]{args.symbol}[/bold green]' -> Provider [bold cyan]{args.provider}[/bold cyan] ticker: '[bold yellow]{res}[/bold yellow]'")
        else:
            print(f"Internal symbol '{args.symbol}' -> Provider '{args.provider}' ticker: '{res}'")


def cmd_get(args):
    loader = DataLoader()
    msg = f"Fetching '[bold green]{args.symbol}[/bold green]' [{args.timeframe}] (start={args.start}, end={args.end})..."
    if HAS_RICH:
        console.print(msg)
    else:
        print(f"Fetching '{args.symbol}' [{args.timeframe}] (start={args.start}, end={args.end})...")

    df = loader.get(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        force_refresh=args.force,
    )

    if df.empty:
        if HAS_RICH:
            console.print("[bold red]No data retrieved.[/bold red]")
        else:
            print("No data retrieved.")
        return

    s_str = str(df.index.min())[:19]
    e_str = str(df.index.max())[:19]

    if HAS_RICH:
        console.print(f"[bold green]Success![/bold green] Retrieved [bold]{len(df):,}[/bold] bars from [cyan]{s_str}[/cyan] to [cyan]{e_str}[/cyan]:")
        
        table = Table(box=box.SIMPLE_HEAVY, header_style="bold magenta")
        table.add_column("Timestamp (UTC)", style="cyan")
        table.add_column("Open", justify="right", style="white")
        table.add_column("High", justify="right", style="green")
        table.add_column("Low", justify="right", style="red")
        table.add_column("Close", justify="right", style="bold white")
        table.add_column("Volume", justify="right", style="yellow")

        display_df = df.head(args.head) if args.head else df.tail(args.tail if args.tail else 10)
        for ts, row in display_df.iterrows():
            ts_label = str(ts)[:19]
            table.add_row(
                ts_label,
                f"{row['open']:.4f}" if row['open'] < 10 else f"{row['open']:.2f}",
                f"{row['high']:.4f}" if row['high'] < 10 else f"{row['high']:.2f}",
                f"{row['low']:.4f}" if row['low'] < 10 else f"{row['low']:.2f}",
                f"{row['close']:.4f}" if row['close'] < 10 else f"{row['close']:.2f}",
                f"{row['volume']:,.2f}" if row['volume'] < 1000 else f"{row['volume']:,.0f}",
            )
        console.print(table)
    else:
        print(f"\nSuccess! Retrieved {len(df)} bars from {s_str} to {e_str}:")
        print("-" * 75)
        display_df = df.head(args.head) if args.head else df.tail(args.tail if args.tail else 10)
        print(display_df)
        print("-" * 75)


def cmd_download_all(args):
    loader = DataLoader()
    cat_str = f" for category '{args.category}'" if args.category else " for all instruments"
    
    if HAS_RICH:
        console.print(f"[bold blue]Starting batch download{cat_str} [timeframe: {args.timeframe}]...[/bold blue]")
    else:
        print(f"Starting batch download{cat_str} [timeframe: {args.timeframe}]...")

    instruments = loader.registry.list_all(args.category)
    results = {}

    if HAS_RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Downloading market data...", total=len(instruments))
            for inst in instruments:
                progress.update(task, description=f"[cyan]Downloading [bold]{inst.symbol}[/bold]...")
                try:
                    df = loader.get(inst.symbol, timeframe=args.timeframe, start=args.start, end=args.end, force_refresh=True)
                    results[inst.symbol] = not df.empty
                except Exception:
                    results[inst.symbol] = False
                progress.advance(task)
    else:
        results = loader.download_all(
            category=args.category,
            timeframe=args.timeframe,
            start=args.start,
            end=args.end,
            max_workers=args.workers,
        )

    succeeded = sum(1 for v in results.values() if v)
    failed = len(results) - succeeded
    if HAS_RICH:
        console.print(f"\n[bold green]Batch download complete:[/bold green] [green]{succeeded} succeeded[/green], [red]{failed} failed[/red] out of {len(results)} total.")
    else:
        print(f"\nBatch download finished: {succeeded} succeeded, {failed} failed out of {len(results)}.")


def cmd_status(args):
    loader = DataLoader()
    info_list = loader.get_cache_status()
    
    if not info_list:
        if HAS_RICH:
            console.print("[yellow]No cached datasets found in data/ directory.[/yellow]")
        else:
            print("\nNo cached datasets found in data/ directory.")
        return

    if HAS_RICH:
        table = Table(
            title=f"Local Parquet Cache Status ({len(info_list)} files)",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("Category", style="magenta", width=12)
        table.add_column("Symbol", style="bold white", width=14)
        table.add_column("TF", style="yellow", width=6, justify="center")
        table.add_column("Bars", justify="right", style="green", width=10)
        table.add_column("File Size", justify="right", style="cyan", width=10)
        table.add_column("Start (UTC)", style="white", width=20)
        table.add_column("End (UTC)", style="white", width=20)

        total_size = 0
        total_rows = 0
        for item in sorted(info_list, key=lambda x: (x.category, x.symbol, x.timeframe)):
            total_size += item.file_size_bytes
            total_rows += item.row_count
            s_str = str(item.start)[:19] if item.start is not pd.NaT else "N/A"
            e_str = str(item.end)[:19] if item.end is not pd.NaT else "N/A"
            table.add_row(
                item.category.capitalize(),
                item.symbol,
                item.timeframe,
                f"{item.row_count:,}",
                format_bytes(item.file_size_bytes),
                s_str,
                e_str,
            )

        console.print(table)
        console.print(f"[bold]Summary:[/bold] [cyan]{len(info_list)}[/cyan] files | [green]{total_rows:,}[/green] total bars | [yellow]{format_bytes(total_size)}[/yellow] disk space\n")
    else:
        print(f"\nCached Datasets ({len(info_list)} files):")
        print("-" * 105)
        print(f"{'Category':<12} {'Symbol':<14} {'TF':<6} {'Rows':<8} {'Size':<10} {'Start (UTC)':<22} {'End (UTC)':<22}")
        print("-" * 105)
        total_size = 0
        total_rows = 0
        for item in sorted(info_list, key=lambda x: (x.category, x.symbol, x.timeframe)):
            total_size += item.file_size_bytes
            total_rows += item.row_count
            s_str = str(item.start)[:19] if item.start is not pd.NaT else "N/A"
            e_str = str(item.end)[:19] if item.end is not pd.NaT else "N/A"
            print(f"{item.category:<12} {item.symbol:<14} {item.timeframe:<6} {item.row_count:<8} {format_bytes(item.file_size_bytes):<10} {s_str:<22} {e_str:<22}")
        print("-" * 105)
        print(f"Total: {len(info_list)} files | {total_rows:,} total bars | {format_bytes(total_size)} disk space\n")


def cmd_sources(args):
    sources = DataLoader.list_sources()
    if HAS_RICH:
        table = Table(
            title=f"Active Market Data Source Plugins ({len(sources)})",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("Plugin Name", style="bold white", width=18)
        table.add_column("Priority", style="yellow", justify="center", width=10)
        table.add_column("Supported Categories", style="green")

        for name, meta in sorted(sources.items(), key=lambda x: x[1]["priority"]):
            cats = ", ".join(meta["supported_categories"]) if meta["supported_categories"] else "All"
            table.add_row(name, str(meta["priority"]), cats)
        console.print(table)
    else:
        print(f"\nActive Data Source Plugins ({len(sources)}):")
        print("-" * 80)
        print(f"{'Source Name':<18} {'Priority':<10} {'Supported Categories'}")
        print("-" * 80)
        for name, meta in sorted(sources.items(), key=lambda x: x[1]["priority"]):
            cats = ", ".join(meta["supported_categories"]) if meta["supported_categories"] else "All"
            print(f"{name:<18} {meta['priority']:<10} {cats}")
        print("-" * 80)


def cmd_keys(args):
    from marketdata.config import get_api_key
    services = [
        ("Alpha Vantage", "alphavantage", "25 requests / day (Free tier)"),
        ("Finnhub", "finnhub", "60 requests / min (Free tier)"),
        ("Tiingo", "tiingo", "500 symbols / mo, 30 req/min (Free tier)"),
        ("Polygon.io", "polygon", "5 requests / min (Free tier)"),
        ("Twelve Data", "twelvedata", "8 requests / min, 800/day (Free tier)"),
    ]
    if HAS_RICH:
        table = Table(
            title="Configured API Keys & Free Provider Status",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("Provider", style="bold white", width=18)
        table.add_column("Status", width=16, justify="center")
        table.add_column("Environment Variable", style="yellow", width=24)
        table.add_column("Free Tier Limits", style="green")

        for name, key_id, limits in services:
            key = get_api_key(key_id)
            status = "[bold green]Configured[/bold green]" if key else "[yellow]Not Set (Optional)[/yellow]"
            env_var = f"{key_id.upper()}_API_KEY"
            table.add_row(name, status, env_var, limits)
        console.print(table)
        console.print("[dim]Note: Zero-key providers (Yahoo Finance, CCXT, Gate.io, MEXC) operate automatically without API keys.[/dim]\n")
    else:
        print("\nConfigured API Keys:")
        print("-" * 80)
        for name, key_id, limits in services:
            key = get_api_key(key_id)
            status = "Configured" if key else "Not Set (Optional)"
            print(f"{name:<18} [{status:<18}] ({key_id.upper()}_API_KEY) - {limits}")
        print("-" * 80)


def cmd_sync(args):
    from marketdata.cron import CronSyncEngine
    engine = CronSyncEngine()
    categories = [args.category] if args.category else None
    timeframes = [args.timeframe] if args.timeframe else ["1d"]
    
    if args.all_timeframes:
        timeframes = ["1d", "1h", "30m", "15m", "5m", "1m"]

    if HAS_RICH:
        console.print(f"[bold blue]Executing incremental delta-sync...[/bold blue] (Categories: {categories or 'All'}, Timeframes: {timeframes}, Overlap: {args.overlap} bars)")
    else:
        print(f"Executing incremental delta-sync... (Categories: {categories or 'All'}, Timeframes: {timeframes}, Overlap: {args.overlap} bars)")

    report = engine.sync(
        categories=categories,
        timeframes=timeframes,
        overlap_bars=args.overlap,
        check_market_hours=not args.ignore_market_hours,
        force=args.force,
    )

    if HAS_RICH:
        table = Table(
            title="Incremental Sync Summary",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("Metric", style="bold white", width=24)
        table.add_column("Value", style="green", width=20)

        table.add_row("Total Series Evaluated", str(report.total_series))
        table.add_row("Successfully Updated", f"[bold green]{report.updated_count}[/bold green]")
        table.add_row("Skipped (Closed Market)", f"[yellow]{report.skipped_closed_count}[/yellow]")
        table.add_row("Errors", f"[red]{report.error_count}[/red]" if report.error_count else "0")
        table.add_row("Total New Bars Added", f"[bold cyan]{report.total_bars_added:,}[/bold cyan]")
        table.add_row("Execution Time", f"{report.duration_seconds:.2f}s")
        console.print(table)
    else:
        print("\nSync Summary:")
        print(f"  Total Series:       {report.total_series}")
        print(f"  Updated:            {report.updated_count}")
        print(f"  Skipped (Closed):   {report.skipped_closed_count}")
        print(f"  Errors:             {report.error_count}")
        print(f"  New Bars Added:     {report.total_bars_added}")
        print(f"  Duration:           {report.duration_seconds:.2f}s")


def cmd_daemon(args):
    import time
    from marketdata.cron import CronSyncEngine
    engine = CronSyncEngine()
    categories = [args.category] if args.category else None
    timeframes = [args.timeframe] if args.timeframe else ["1h"]
    interval = args.interval_seconds

    if HAS_RICH:
        console.print(f"[bold green]Starting MarketData Daemon[/bold green] (Interval: {interval}s, Timeframes: {timeframes}). Press Ctrl+C to stop.")
    else:
        print(f"Starting MarketData Daemon (Interval: {interval}s, Timeframes: {timeframes}). Press Ctrl+C to stop.")

    try:
        while True:
            t_now = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            if HAS_RICH:
                console.print(f"[{t_now}] [cyan]Running scheduled sync...[/cyan]")
            else:
                print(f"[{t_now}] Running scheduled sync...")

            report = engine.sync(categories=categories, timeframes=timeframes, check_market_hours=True)
            msg = f"Sync done: {report.updated_count} updated, {report.total_bars_added} bars added in {report.duration_seconds:.2f}s. Sleeping {interval}s..."
            if HAS_RICH:
                console.print(f"[green]{msg}[/green]")
            else:
                print(msg)
            time.sleep(interval)
    except KeyboardInterrupt:
        if HAS_RICH:
            console.print("\n[yellow]Daemon stopped by user.[/yellow]")
        else:
            print("\nDaemon stopped by user.")


def cmd_generate_cron(args):
    from marketdata.cron import generate_crontab_entries, generate_systemd_service, generate_systemd_timer
    from marketdata.config import BASE_DIR

    crontab_text = generate_crontab_entries()
    service_text = generate_systemd_service()
    timer_text = generate_systemd_timer()

    scripts_dir = BASE_DIR / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    (scripts_dir / "crontab.txt").write_text(crontab_text, encoding="utf-8")
    (scripts_dir / "marketdata-sync.service").write_text(service_text, encoding="utf-8")
    (scripts_dir / "marketdata-sync.timer").write_text(timer_text, encoding="utf-8")

    if HAS_RICH:
        console.print("[bold green]Generated deployment files in scripts/:[/bold green]")
        console.print("  - [cyan]scripts/crontab.txt[/cyan] (Crontab configuration)")
        console.print("  - [cyan]scripts/marketdata-sync.service[/cyan] (Systemd service unit)")
        console.print("  - [cyan]scripts/marketdata-sync.timer[/cyan] (Systemd timer unit)")
        console.print("\n[bold]Crontab preview:[/bold]")
        console.print(Panel(crontab_text.strip(), box=box.ROUNDED, border_style="cyan"))
    else:
        print("\nGenerated deployment files in scripts/:")
        print("  - scripts/crontab.txt")
        print("  - scripts/marketdata-sync.service")
        print("  - scripts/marketdata-sync.timer\n")
        print(crontab_text)


def cmd_export_mappings(args):
    if HAS_RICH:
        console.print("[bold blue]Exporting mappings to JSON and Markdown...[/bold blue]")
    else:
        print("Exporting mappings to JSON and Markdown...")
    generate_mappings_and_table()
    if HAS_RICH:
        console.print("[bold green]Export complete:[/bold green] updated [cyan]'ticker_mappings.json'[/cyan] and [cyan]'TICKER_CONVERSION_TABLE.md'[/cyan].")
    else:
        print("Export complete: 'ticker_mappings.json' and 'TICKER_CONVERSION_TABLE.md' updated.")


def main():
    parser = argparse.ArgumentParser(description="MarketData: Universal Historical Market Data Downloader & Cache")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list
    p_list = subparsers.add_parser("list", help="List tradeable instruments")
    p_list.add_argument("--category", "-c", choices=["crypto", "stocks", "commodities", "indices", "forex"], help="Filter by category")

    # info
    p_info = subparsers.add_parser("info", help="Show instrument details and provider mappings")
    p_info.add_argument("symbol", help="Instrument symbol (e.g. BTCUSD, AAPL, EURUSD)")

    # convert
    p_conv = subparsers.add_parser("convert", help="Translate ticker to/from provider formats")
    p_conv.add_argument("symbol", help="Symbol to convert")
    p_conv.add_argument("--provider", "-p", default="yfinance", choices=["yfinance", "gateio", "mexc", "coinbase"], help="Target provider")
    p_conv.add_argument("--reverse", "-r", action="store_true", help="Convert from provider symbol back to internal symbol")

    # get
    p_get = subparsers.add_parser("get", help="Get on-demand historical data for a symbol")
    p_get.add_argument("symbol", help="Instrument symbol")
    p_get.add_argument("--timeframe", "-t", default="1d", help="Timeframe interval (1m, 5m, 15m, 1h, 1d)")
    p_get.add_argument("--start", "-s", default=None, help="Start date (YYYY-MM-DD)")
    p_get.add_argument("--end", "-e", default=None, help="End date (YYYY-MM-DD)")
    p_get.add_argument("--force", "-f", action="store_true", help="Force refresh from remote providers")
    p_get.add_argument("--head", type=int, default=0, help="Print first N rows")
    p_get.add_argument("--tail", type=int, default=5, help="Print last N rows")

    # download-all
    p_all = subparsers.add_parser("download-all", help="Batch download historical data")
    p_all.add_argument("--category", "-c", choices=["crypto", "stocks", "commodities", "indices", "forex"], help="Filter by category")
    p_all.add_argument("--timeframe", "-t", default="1d", help="Timeframe interval")
    p_all.add_argument("--start", "-s", default=None, help="Start date")
    p_all.add_argument("--end", "-e", default=None, help="End date")
    p_all.add_argument("--workers", "-w", type=int, default=5, help="Concurrent download workers")

    # sync (cron delta-sync)
    p_sync = subparsers.add_parser("sync", help="Execute server-optimized incremental delta sync")
    p_sync.add_argument("--category", "-c", choices=["crypto", "stocks", "commodities", "indices", "forex"], help="Filter by category")
    p_sync.add_argument("--timeframe", "-t", default="1d", help="Timeframe interval")
    p_sync.add_argument("--all-timeframes", action="store_true", help="Sync across all 6 timeframes (1d, 1h, 30m, 15m, 5m, 1m)")
    p_sync.add_argument("--overlap", type=int, default=2, help="Number of overlap bars to re-fetch for candle finalization")
    p_sync.add_argument("--ignore-market-hours", action="store_true", help="Do not skip closed markets")
    p_sync.add_argument("--force", "-f", action="store_true", help="Force sync regardless of market status")

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="Run recurring sync daemon")
    p_daemon.add_argument("--interval-seconds", "-i", type=int, default=3600, help="Interval in seconds between syncs (default: 3600s)")
    p_daemon.add_argument("--category", "-c", choices=["crypto", "stocks", "commodities", "indices", "forex"], help="Filter by category")
    p_daemon.add_argument("--timeframe", "-t", default="1h", help="Timeframe interval")

    # generate-cron
    subparsers.add_parser("generate-cron", help="Generate Crontab and Systemd deployment templates")

    # status
    subparsers.add_parser("status", help="Show status of local cached data")

    # sources
    subparsers.add_parser("sources", help="List registered market data plugins")

    # keys
    subparsers.add_parser("keys", help="Show configured optional API keys status")

    # export-mappings
    subparsers.add_parser("export-mappings", help="Export conversion table and mappings")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "convert":
        cmd_convert(args)
    elif args.command == "get":
        cmd_get(args)
    elif args.command == "download-all":
        cmd_download_all(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "daemon":
        cmd_daemon(args)
    elif args.command == "generate-cron":
        cmd_generate_cron(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "sources":
        cmd_sources(args)
    elif args.command == "keys":
        cmd_keys(args)
    elif args.command == "export-mappings":
        cmd_export_mappings(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
