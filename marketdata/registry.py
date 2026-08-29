"""Instrument Registry and Symbol Resolution Engine.

Parses info.md to dynamically discover tradeable broker assets, leverage parameters,
and maps internal broker symbols to external market data provider identifiers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import re

from marketdata.config import INFO_FILE


@dataclass
class Instrument:
    symbol: str
    category: str  # crypto, stocks, commodities, indices, forex
    max_leverage_long: str
    max_leverage_short: str
    commission: str
    trading_hours: str
    overnight_swap: str
    trading_size: str
    
    # Provider-specific mapped symbols
    yfinance_ticker: Optional[str] = None
    gateio_pair: Optional[str] = None
    mexc_symbol: Optional[str] = None
    coinbase_product: Optional[str] = None

    def __repr__(self) -> str:
        return f"<Instrument {self.symbol} [{self.category}] (Lev: {self.max_leverage_long}/{self.max_leverage_short})>"


class InstrumentRegistry:
    """Registry maintaining metadata and external symbol resolution for all broker instruments."""

    def __init__(self, info_path: Path = INFO_FILE):
        self.info_path = Path(info_path)
        self._instruments: Dict[str, Instrument] = {}
        self._categories: Dict[str, List[Instrument]] = {
            "crypto": [],
            "stocks": [],
            "commodities": [],
            "indices": [],
            "forex": [],
        }
        self._load_and_parse()

    def _load_and_parse(self) -> None:
        if not self.info_path.exists():
            raise FileNotFoundError(f"info.md not found at {self.info_path}")

        with open(self.info_path, "r", encoding="utf-8") as f:
            content = f.read()

        current_category = None
        
        general_commission = "0.03% of notional"
        forex_commission = "0.01% of notional"
        general_hours = "24/7"
        forex_hours = "24/5 Sun 21:05 to Fri 20:55 UTC"
        general_swap = "0.05% of notional per night"
        forex_swap = "0.05% per night (3x Wednesday)"
        general_size = "Notional amount"
        forex_size = "1 lot = 100,000 units base currency"

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("# "):
                header = line[2:].strip().lower()
                if "crypto" in header:
                    current_category = "crypto"
                elif "stock" in header:
                    current_category = "stocks"
                elif "commodit" in header:
                    current_category = "commodities"
                elif "indic" in header:
                    current_category = "indices"
                elif "forex" in header or "fx" in header:
                    current_category = "forex"
                continue

            if current_category and "," in line:
                parts = [p.strip() for p in line.split(",")]
                symbol = parts[0]
                if symbol.lower() in ["condition", "commission", "trading hours", "overnight swap", "trading size"]:
                    continue

                lev_long = parts[1] if len(parts) > 1 else "1x"
                lev_short = parts[2] if len(parts) > 2 else lev_long

                is_forex = current_category == "forex"
                inst = Instrument(
                    symbol=symbol,
                    category=current_category,
                    max_leverage_long=lev_long,
                    max_leverage_short=lev_short,
                    commission=forex_commission if is_forex else general_commission,
                    trading_hours=forex_hours if is_forex else general_hours,
                    overnight_swap=forex_swap if is_forex else general_swap,
                    trading_size=forex_size if is_forex else general_size,
                )
                self._resolve_provider_tickers(inst)
                self._instruments[symbol] = inst
                self._categories[current_category].append(inst)

    def _resolve_provider_tickers(self, inst: Instrument) -> None:
        sym = inst.symbol
        cat = inst.category

        if cat == "forex":
            inst.yfinance_ticker = f"{sym}=X"

        elif cat == "commodities":
            commodity_map = {
                "CL": "CL=F",       # Crude Oil
                "COPPER": "HG=F",   # Copper
                "NATGAS": "NG=F",   # Natural Gas
                "XAG": "SI=F",      # Silver Futures
                "XAU": "GC=F",      # Gold Futures
                "XPD": "PA=F",      # Palladium
                "XPT": "PL=F",      # Platinum
            }
            inst.yfinance_ticker = commodity_map.get(sym.upper(), f"{sym}=F")

        elif cat == "indices":
            indices_map = {
                "SPY": "SPY",
                "QQQ": "QQQ",
                "IWM": "IWM",
                "EWJ": "EWJ",
                "EWY": "EWY",
                "EWZ": "EWZ",
                "STXX": "EZU",
            }
            inst.yfinance_ticker = indices_map.get(sym.upper(), sym)

        elif cat == "stocks":
            stock_map = {
                "BRKB": "BRK-B",
                "HYUNDAI": "005380.KS",
                "SAMSUNG": "005930.KS",
            }
            inst.yfinance_ticker = stock_map.get(sym.upper(), sym)

        elif cat == "crypto":
            if sym.endswith("USD") and len(sym) > 3:
                coin = sym[:-3]
            elif sym.endswith("USDT") and len(sym) > 4:
                coin = sym[:-4]
            else:
                coin = sym

            inst.yfinance_ticker = f"{coin}-USD"
            inst.gateio_pair = f"{coin}_USDT"
            inst.mexc_symbol = f"{coin}USDT"
            inst.coinbase_product = f"{coin}-USD"

    def get(self, symbol: str) -> Optional[Instrument]:
        """Look up an instrument by symbol (case-insensitive)."""
        sym_upper = symbol.strip().upper()
        if sym_upper in self._instruments:
            return self._instruments[sym_upper]
        clean = re.sub(r"[-_=X/]", "", sym_upper)
        for s, inst in self._instruments.items():
            if re.sub(r"[-_=X/]", "", s) == clean:
                return inst
        return None

    def list_all(self, category: Optional[str] = None) -> List[Instrument]:
        """List all instruments, optionally filtered by category."""
        if category:
            cat_lower = category.lower()
            return self._categories.get(cat_lower, [])
        return list(self._instruments.values())

    @property
    def categories(self) -> Dict[str, List[Instrument]]:
        return self._categories


_registry_instance: Optional[InstrumentRegistry] = None

def get_registry(info_path: Path = INFO_FILE) -> InstrumentRegistry:
    global _registry_instance
    if _registry_instance is None or _registry_instance.info_path != info_path:
        _registry_instance = InstrumentRegistry(info_path)
    return _registry_instance
