"""MarketData Windows System Tray - Tailscale-style.

Click the tray icon (left or right) to open a native popup menu.
No GUI windows. No dialogs. Just the menu.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import logging
import subprocess
import sys
import threading
import time
import winreg
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PIL import Image, ImageDraw

try:
    from pystray import Icon, Menu, MenuItem
except ImportError:
    sys.exit("pystray is required: pip install pystray pillow")

from marketdata.config import DATA_DIR, LOGS_DIR, get_user_config, set_user_config_value
from marketdata.cron import CronSyncEngine, SyncReport

LOGS_DIR.mkdir(parents=True, exist_ok=True)
_handler = logging.FileHandler(LOGS_DIR / "tray.log", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger = logging.getLogger("marketdata.tray")
logger.setLevel(logging.INFO)
logger.addHandler(_handler)

APP_NAME        = "MarketDataTray"
MUTEX_NAME      = "MarketData_Tray_SingleInstance_Mutex"
STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

AUTO_SYNC_OPTIONS: dict[str, int] = {
    "Disabled":       0,
    "Every 15 min":   15 * 60,
    "Every 1 hour":   60 * 60,
    "Every 4 hours":   4 * 60 * 60,
    "Every 24 hours": 24 * 60 * 60,
}


# ---------------------------------------------------------------------------
# Single-instance mutex
# ---------------------------------------------------------------------------

def _acquire_mutex() -> Optional[int]:
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype  = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    k32.GetLastError.restype  = ctypes.c_uint32
    h = k32.CreateMutexW(None, True, MUTEX_NAME)
    if k32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        if h:
            k32.CloseHandle(ctypes.c_void_p(h))
        return None
    return h


def _release_mutex(h: Optional[int]) -> None:
    if h:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(h))


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def _copy_to_clipboard(text: str) -> bool:
    """Write text to the Windows clipboard."""
    try:
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        encoded  = (text + "\0").encode("utf-16-le")
        for _ in range(5):
            if u32.OpenClipboard(None):
                try:
                    u32.EmptyClipboard()
                    hm = k32.GlobalAlloc(0x0002, len(encoded))
                    pm = k32.GlobalLock(hm)
                    ctypes.memmove(pm, encoded, len(encoded))
                    k32.GlobalUnlock(hm)
                    u32.SetClipboardData(13, hm)
                    return True
                finally:
                    u32.CloseClipboard()
            time.sleep(0.05)
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Windows startup registry
# ---------------------------------------------------------------------------

def _startup_cmd() -> str:
    vbs_path = _ROOT / "Start_MarketData_Tray.vbs"
    return f'wscript.exe "{vbs_path}"'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0,
                            winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def _enable_startup() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _startup_cmd())


def _disable_startup() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Icon rendering
# ---------------------------------------------------------------------------

_BADGE_COLORS: dict[str, tuple[int, int, int, int]] = {
    "idle":    ( 59, 130, 246, 255),
    "syncing": (234, 179,   8, 255),
    "ok":      ( 34, 197,  94, 255),
    "error":   (239,  68,  68, 255),
}


def _make_icon(state: str = "idle") -> Image.Image:
    """64x64 RGBA icon: dark tile + three candlestick bars + state badge."""
    S    = 64
    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        [3, 3, S - 3, S - 3], radius=13,
        fill=(22, 27, 34, 245), outline=(48, 54, 61, 255), width=2,
    )

    # Candle 1 - bullish green
    draw.line([(17, 13), (17, 50)], fill=(46, 160, 67, 255), width=2)
    draw.rounded_rectangle([12, 21, 22, 41], radius=2, fill=(46, 160, 67, 255))

    # Candle 2 - bearish red
    draw.line([(31, 19), (31, 51)], fill=(248, 81, 73, 255), width=2)
    draw.rounded_rectangle([26, 27, 36, 45], radius=2, fill=(248, 81, 73, 255))

    # Candle 3 - blue
    draw.line([(45, 9), (45, 43)], fill=(56, 189, 248, 255), width=2)
    draw.rounded_rectangle([40, 15, 50, 35], radius=2, fill=(56, 189, 248, 255))

    # State badge (bottom-right)
    color = _BADGE_COLORS.get(state, _BADGE_COLORS["idle"])
    draw.ellipse([45, 45, 59, 59], fill=color, outline=(22, 27, 34, 255), width=2)

    return img


# ---------------------------------------------------------------------------
# Left-click -> menu (Tailscale style)
# ---------------------------------------------------------------------------

def _patch_left_click(icon: Icon) -> None:
    """Route WM_LBUTTONUP to WM_RBUTTONUP so left-click opens the context menu."""
    try:
        import pystray._win32 as _mod
        w32      = _mod.win32
        handlers = icon._message_handlers
        orig     = handlers[w32.WM_NOTIFY]

        def _on_notify(wparam, lparam):
            if lparam == w32.WM_LBUTTONUP:
                lparam = w32.WM_RBUTTONUP
            return orig(wparam, lparam)

        handlers[w32.WM_NOTIFY] = _on_notify
    except Exception as exc:
        logger.warning("Left-click patch failed (right-click only): %s", exc)


# ---------------------------------------------------------------------------
# Tray application
# ---------------------------------------------------------------------------

class TrayApp:
    """System-tray icon + popup menu controller."""

    def __init__(self) -> None:
        cfg = get_user_config()
        self.auto_interval: int = int(cfg.get("auto_sync_interval", 3600))

        self._syncing           = False
        self._last_sync_time: Optional[datetime.datetime] = None
        self._last_sync_summary = "No sync yet"

        self._stop      = threading.Event()
        self._sync_wake = threading.Event()
        self._icon: Optional[Icon] = None

    # -- Status ---------------------------------------------------------------

    def _status_line(self) -> str:
        if self._syncing:
            return "Syncing..."
        if self._last_sync_time:
            t = self._last_sync_time.strftime("%H:%M:%S")
            return "Last sync: " + t + "  " + self._last_sync_summary
        return "Idle - no sync run yet"

    # -- Notifications --------------------------------------------------------

    def _notify(self, title: str, body: str) -> None:
        if self._icon:
            try:
                self._icon.notify(body, title)
            except Exception:
                pass

    # -- Icon state -----------------------------------------------------------

    def _set_state(self, state: str) -> None:
        if self._icon:
            try:
                self._icon.icon  = _make_icon(state)
                self._icon.title = "MarketData  -  " + self._status_line()
            except Exception:
                pass

    # -- Sync worker ----------------------------------------------------------

    def _run_sync(self, categories: list[str] | None = None, timeframes: list[str] | None = None, force: bool = False) -> None:
        if self._syncing:
            self._notify("MarketData", "A sync is already in progress.")
            return

        tfs = ", ".join(timeframes) if timeframes else "1h"
        cats = ", ".join(categories).title() if categories else "All Assets"
        msg = f"Starting sync for: {cats} ({tfs})" + (" (Forced)" if force else "")
        self._notify("Sync Started", msg)

        def _worker() -> None:
            self._syncing = True
            self._set_state("syncing")
            
            def _progress_cb(current: int, total: int, symbol: str, tf: str) -> bool:
                if self._stop.is_set():
                    return False
                pct = int(current / total * 100) if total > 0 else 0
                self._last_sync_summary = f"[{pct}%] {current}/{total} - {symbol} ({tf})"
                if self._icon:
                    try:
                        self._icon.title = f"MarketData - {self._last_sync_summary}"
                    except Exception:
                        pass
                return True

            try:
                report: SyncReport = CronSyncEngine().sync(
                    categories=categories,
                    timeframes=timeframes or ["1h"],
                    check_market_hours=not force,
                    force=force,
                    progress_callback=_progress_cb
                )
                self._last_sync_time    = datetime.datetime.now()
                errors = (", " + str(report.error_count) + " error(s)") if report.error_count else ""
                self._last_sync_summary = (
                    "+" + str(report.total_bars_added) + " bars, "
                    + str(report.updated_count) + " updated "
                    + "(" + str(round(report.duration_seconds, 1)) + "s)" + errors
                )
                self._set_state("ok")
                self._notify("Sync complete", self._last_sync_summary)
                time.sleep(5)
                if not self._syncing:
                    self._set_state("idle")
            except Exception as exc:
                self._last_sync_summary = "Error: " + str(exc)
                self._set_state("error")
                self._notify("Sync failed", str(exc))
                logger.exception("Sync error")
                time.sleep(5)
                if not self._syncing:
                    self._set_state("idle")
            finally:
                self._syncing = False

        threading.Thread(target=_worker, daemon=False, name="md-sync").start()

    # -- Auto-sync loop -------------------------------------------------------

    def _auto_sync_loop(self) -> None:
        """Sleep for auto_interval seconds, then trigger 1h sync.
        Uses Event.wait() so interval changes or shutdown take effect immediately.
        """
        while not self._stop.is_set():
            interval = self.auto_interval
            if interval <= 0:
                self._sync_wake.wait(timeout=60)
                self._sync_wake.clear()
                continue

            fired_by_timeout = not self._sync_wake.wait(timeout=interval)
            self._sync_wake.clear()

            if self._stop.is_set():
                break

            if fired_by_timeout:
                self._run_sync(timeframes=["1h"], force=False)

    # -- Menu actions ---------------------------------------------------------

    def _toggle_startup(self) -> None:
        if is_startup_enabled():
            _disable_startup()
            self._notify("MarketData", "Removed from Windows startup.")
        else:
            _enable_startup()
            self._notify("MarketData", "Will start automatically on login.")
        if self._icon:
            self._icon.update_menu()

    def _set_interval(self, seconds: int) -> None:
        self.auto_interval = seconds
        set_user_config_value("auto_sync_interval", seconds)
        label = next((k for k, v in AUTO_SYNC_OPTIONS.items() if v == seconds), "custom")
        self._notify("Auto-sync", "Interval: " + label)
        self._sync_wake.set()
        if self._icon:
            self._icon.update_menu()

    def _copy_data_path(self) -> None:
        p = str(DATA_DIR.resolve())
        _copy_to_clipboard(p)
        self._notify("Copied", p)

    def _open_data_folder(self) -> None:
        subprocess.Popen(["explorer", str(DATA_DIR)])

    def _quit(self) -> None:
        self._stop.set()
        self._sync_wake.set()
        if self._icon:
            self._icon.stop()

    # -- Menu -----------------------------------------------------------------

    def _make_interval_item(self, label: str, secs: int) -> MenuItem:
        """Factory — produces a MenuItem with correct-arity callables for pystray."""
        app = self
        return MenuItem(
            label,
            action=lambda _i, _it: app._set_interval(secs),   # action: 2 args
            checked=lambda _it: app.auto_interval == secs,      # checked: 1 arg
            radio=True,
        )

    def _build_menu(self) -> Menu:
        interval_items = [
            self._make_interval_item(label, secs)
            for label, secs in AUTO_SYNC_OPTIONS.items()
        ]

        def _sync_action(cat: str | None, tf: str | None, force: bool = False):
            return lambda _i, _it: self._run_sync(
                categories=[cat] if cat else None,
                timeframes=[tf] if tf else ["1h"],
                force=force
            )

        def _make_cat_submenu(cat: str | None) -> Menu:
            return Menu(
                MenuItem("Sync 1h", _sync_action(cat, "1h")),
                MenuItem("Sync 1d", _sync_action(cat, "1d")),
                Menu.SEPARATOR,
                MenuItem("Sync 1m", _sync_action(cat, "1m")),
                MenuItem("Sync 5m", _sync_action(cat, "5m")),
                MenuItem("Sync 15m", _sync_action(cat, "15m")),
                MenuItem("Sync 30m", _sync_action(cat, "30m")),
                MenuItem("Sync 4h", _sync_action(cat, "4h")),
                Menu.SEPARATOR,
                MenuItem("Sync All Timeframes", lambda _i, _it: self._run_sync(
                    categories=[cat] if cat else None,
                    timeframes=["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
                ))
            )

        sync_menu = Menu(
            MenuItem("All Assets", _make_cat_submenu(None)),
            Menu.SEPARATOR,
            MenuItem("Crypto", _make_cat_submenu("crypto")),
            MenuItem("Stocks", _make_cat_submenu("stocks")),
            MenuItem("Forex", _make_cat_submenu("forex")),
            MenuItem("Commodities", _make_cat_submenu("commodities")),
            MenuItem("Indices", _make_cat_submenu("indices")),
            Menu.SEPARATOR,
            MenuItem("Force refresh 1h (ignore hours)", _sync_action(None, "1h", force=True))
        )

        return Menu(
            # text callable: 1 arg (the MenuItem); action=None → non-clickable
            MenuItem(lambda _it: self._status_line(), action=None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Sync Data Now", sync_menu),
            Menu.SEPARATOR,
            MenuItem("Copy data path",          lambda _i, _it: self._copy_data_path()),
            MenuItem("Open data folder",        lambda _i, _it: self._open_data_folder()),
            Menu.SEPARATOR,
            MenuItem(
                "Run on Windows startup",
                action=lambda _i, _it: self._toggle_startup(),
                checked=lambda _it: is_startup_enabled(),       # checked: 1 arg
            ),
            MenuItem("Auto-sync interval", Menu(*interval_items)),
            Menu.SEPARATOR,
            MenuItem("Quit", lambda _i, _it: self._quit()),
        )


    # -- Run ------------------------------------------------------------------

    def run(self) -> None:
        self._auto_thread = threading.Thread(
            target=self._auto_sync_loop, daemon=False, name="md-autosync",
        )
        self._auto_thread.start()

        self._icon = Icon(
            name="MarketData",
            icon=_make_icon("idle"),
            title="MarketData",
            menu=self._build_menu(),
        )

        def _on_ready(icon: Icon) -> None:
            icon.visible = True
            _patch_left_click(icon)
            logger.info("MarketData tray running.")

        self._icon.run(setup=_on_ready)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="MarketData system tray")
    ap.add_argument("--install-startup", action="store_true",
                    help="Register tray in Windows startup and exit")
    ap.add_argument("--remove-startup",  action="store_true",
                    help="Remove tray from Windows startup and exit")
    ap.add_argument("--status",          action="store_true",
                    help="Print startup/path status and exit")
    args = ap.parse_args()

    if args.install_startup:
        _enable_startup()
        print("Startup enabled.\nCommand: " + _startup_cmd())
        return

    if args.remove_startup:
        _disable_startup()
        print("Startup entry removed.")
        return

    if args.status:
        print("Startup enabled : " + str(is_startup_enabled()))
        print("Startup command : " + _startup_cmd())
        print("Data directory  : " + str(DATA_DIR))
        return

    h = _acquire_mutex()
    if h is None:
        print("MarketData tray is already running.")
        return

    try:
        TrayApp().run()
    except Exception:
        logger.exception("Fatal error in tray app")
    finally:
        _release_mutex(h)


if __name__ == "__main__":
    main()
