"""Ticker Conversion Engine and Strongly-Typed Mapping Objects.

Provides structured Python objects (TickerMapping, TickerConversionTable) and
bidirectional translation between internal broker symbols and external providers
(Yahoo Finance, Gate.io, MEXC, Coinbase, Kraken, etc.).
"""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
import pandas as pd

from marketdata.config import BASE_DIR, INFO_FILE
from marketdata.registry import Instrument, get_registry

MAPPINGS_FILE = BASE_DIR / "ticker_mappings.json"
CUSTOM_MAPPINGS_FILE = BASE_DIR / "custom_mappings.json"
MARKDOWN_TABLE_FILE = BASE_DIR / "TICKER_CONVERSION_TABLE.md"


@dataclass
class TickerMapping:
    """Strongly-typed object representing provider ticker mappings for a single instrument."""

    symbol: str
    category: str
    max_leverage_long: str
    max_leverage_short: str
    yfinance: Optional[str] = None
    gateio: Optional[str] = None
    mexc: Optional[str] = None
    coinbase: Optional[str] = None
    extra_providers: Dict[str, str] = field(default_factory=dict)

    def get_provider_ticker(self, provider: str) -> Optional[str]:
        """Retrieve external ticker for a given provider name (case-insensitive)."""
        p_lower = provider.lower()
        if p_lower in ["yfinance", "yf", "yahoo"]:
            return self.yfinance
        elif p_lower in ["gate", "gateio"]:
            return self.gateio
        elif p_lower in ["mexc"]:
            return self.mexc
        elif p_lower in ["coinbase", "cb"]:
            return self.coinbase
        return self.extra_providers.get(p_lower)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize mapping object to clean dictionary."""
        d = {
            "symbol": self.symbol,
            "category": self.category,
            "max_leverage_long": self.max_leverage_long,
            "max_leverage_short": self.max_leverage_short,
            "yfinance": self.yfinance or "",
            "gateio": self.gateio or "",
            "mexc": self.mexc or "",
            "coinbase": self.coinbase or "",
        }
        if self.extra_providers:
            d["extra_providers"] = self.extra_providers
        return d

    def __repr__(self) -> str:
        providers = []
        if self.yfinance:
            providers.append(f"yf='{self.yfinance}'")
        if self.gateio:
            providers.append(f"gate='{self.gateio}'")
        if self.mexc:
            providers.append(f"mexc='{self.mexc}'")
        if self.coinbase:
            providers.append(f"coinbase='{self.coinbase}'")
        prov_str = ", ".join(providers) if providers else "No providers"
        return f"<TickerMapping {self.symbol} [{self.category}] ({prov_str})>"


class TickerConversionTable:
    """
    Python object representing the complete collection of ticker conversions.
    Allows dict-like access, category filtering, dataframe conversion, and exports.
    """

    def __init__(self, info_path: Path = INFO_FILE, custom_file: Path = CUSTOM_MAPPINGS_FILE):
        self.info_path = Path(info_path)
        self.custom_file = Path(custom_file)
        self._mappings: Dict[str, TickerMapping] = {}
        self._by_category: Dict[str, List[TickerMapping]] = {
            "crypto": [],
            "stocks": [],
            "commodities": [],
            "indices": [],
            "forex": [],
        }
        self._reverse_lookups: Dict[str, Dict[str, str]] = {}
        self._build_table()

    def _build_table(self) -> None:
        registry = get_registry(self.info_path)
        custom_mappings: Dict[str, Dict[str, str]] = {}

        if self.custom_file.exists():
            try:
                with open(self.custom_file, "r", encoding="utf-8") as f:
                    custom_mappings = json.load(f)
            except Exception:
                custom_mappings = {}

        for inst in registry.list_all():
            sym = inst.symbol
            custom = custom_mappings.get(sym, {})

            mapping = TickerMapping(
                symbol=sym,
                category=inst.category,
                max_leverage_long=inst.max_leverage_long,
                max_leverage_short=inst.max_leverage_short,
                yfinance=custom.get("yfinance", inst.yfinance_ticker),
                gateio=custom.get("gateio", inst.gateio_pair),
                mexc=custom.get("mexc", inst.mexc_symbol),
                coinbase=custom.get("coinbase", inst.coinbase_product),
                extra_providers={k: v for k, v in custom.items() if k not in ["yfinance", "gateio", "mexc", "coinbase"]},
            )

            self._mappings[sym] = mapping
            self._by_category.setdefault(inst.category, []).append(mapping)

            # Build reverse lookup index for O(1) searches
            for prov, ticker in [
                ("yfinance", mapping.yfinance),
                ("gateio", mapping.gateio),
                ("mexc", mapping.mexc),
                ("coinbase", mapping.coinbase),
            ]:
                if ticker:
                    self._reverse_lookups.setdefault(prov, {})[ticker] = sym
            for prov, ticker in mapping.extra_providers.items():
                if ticker:
                    self._reverse_lookups.setdefault(prov, {})[ticker] = sym

    def __getitem__(self, symbol: str) -> TickerMapping:
        sym_upper = symbol.strip().upper()
        if sym_upper in self._mappings:
            return self._mappings[sym_upper]
        raise KeyError(f"Symbol '{symbol}' not found in TickerConversionTable.")

    def __contains__(self, symbol: str) -> bool:
        return symbol.strip().upper() in self._mappings

    def __len__(self) -> int:
        return len(self._mappings)

    def __iter__(self) -> Iterator[TickerMapping]:
        return iter(self._mappings.values())

    def get(self, symbol: str) -> Optional[TickerMapping]:
        """Retrieve TickerMapping object for a symbol (case-insensitive)."""
        return self._mappings.get(symbol.strip().upper())

    def by_category(self, category: str) -> List[TickerMapping]:
        """Retrieve all TickerMapping objects for an asset category."""
        return self._by_category.get(category.lower(), [])

    def to_provider(self, symbol: str, provider: str = "yfinance") -> Optional[str]:
        """Forward conversion: internal broker symbol -> provider ticker."""
        mapping = self.get(symbol)
        if not mapping:
            return None
        return mapping.get_provider_ticker(provider)

    def from_provider(self, provider_ticker: str, provider: str = "yfinance") -> Optional[str]:
        """Reverse conversion: provider ticker -> internal broker symbol."""
        p_clean = provider_ticker.strip()
        p_lower = provider.lower()
        if p_lower in ["yf", "yahoo"]:
            p_lower = "yfinance"
        elif p_lower in ["gate"]:
            p_lower = "gateio"
        elif p_lower in ["cb"]:
            p_lower = "coinbase"

        prov_index = self._reverse_lookups.get(p_lower, {})
        return prov_index.get(p_clean)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert entire conversion table to a pandas DataFrame."""
        rows = [m.to_dict() for m in self._mappings.values()]
        return pd.DataFrame(rows)

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Convert to nested dictionary keyed by symbol."""
        return {m.symbol: m.to_dict() for m in self._mappings.values()}

    def export_json(self, output_path: Path = MAPPINGS_FILE) -> Path:
        """Export all mappings as a clean JSON dictionary."""
        data = self.to_dict()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return output_path

    def export_markdown_table(self, output_path: Path = MARKDOWN_TABLE_FILE) -> Path:
        """Export a comprehensive Markdown conversion table."""
        lines = [
            "# Ticker Conversion Table",
            "",
            "This table defines the bidirectional mappings between internal broker symbols and external market data providers.",
            "",
            f"**Total Tradeable Instruments**: {len(self._mappings)}",
            "",
        ]

        categories = ["crypto", "stocks", "commodities", "indices", "forex"]
        for cat in categories:
            cat_rows = self.by_category(cat)
            if not cat_rows:
                continue

            lines.append(f"## {cat.capitalize()} ({len(cat_rows)} symbols)")
            lines.append("")
            lines.append("| Internal Symbol | Max Leverage (L/S) | Yahoo Finance | Gate.io Pair | MEXC Symbol | Coinbase Product |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for m in cat_rows:
                lev = f"{m.max_leverage_long}/{m.max_leverage_short}"
                yf = f"`{m.yfinance}`" if m.yfinance else "-"
                gate = f"`{m.gateio}`" if m.gateio else "-"
                mexc = f"`{m.mexc}`" if m.mexc else "-"
                cb = f"`{m.coinbase}`" if m.coinbase else "-"
                lines.append(f"| **{m.symbol}** | {lev} | {yf} | {gate} | {mexc} | {cb} |")
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path


TickerConverter = TickerConversionTable


def load_ticker_conversions(info_path: Path = INFO_FILE) -> TickerConversionTable:
    """Helper function to load the full TickerConversionTable object."""
    return TickerConversionTable(info_path=info_path)


def generate_mappings_and_table() -> None:
    """Generate both JSON mapping and Markdown table files."""
    table = TickerConversionTable()
    table.export_json()
    table.export_markdown_table()
