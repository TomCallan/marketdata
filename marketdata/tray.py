"""Windows System Tray Notification Area Application for MarketData Toolkit.

Provides a lightweight, background tray icon in the Windows taskbar overflow area:
- View real-time and last sync status & statistics
- Trigger on-demand delta-syncs (1h, 1d, all timeframes, or force refresh)
- Native Windows context menu on left- or right-click (menu-only, no GUI windows)
- One-click copy of Market Data paths to clipboard
- Open cache directory in Windows File Explorer
- Toggle automatic start on Windows boot (via HKCU Run registry)
- Configurable background auto-sync scheduler
"""

import argparse
import ctypes
from dataclasses import dataclass
import datetime
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import List, Optional
import winreg

# Ensure package root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image, ImageDraw

try:
    import pystray
    from pystray import Icon, Menu, MenuItem
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

from marketdata.config import BASE_DIR, DATA_DIR, LOGS_DIR, get_user_config, set_user_config_value
from marketdata.cron import CronSyncEngine, SyncReport
from marketdata.registry import get_registry

# Setup file logging for tray app
TRAY_LOG_FILE = LOGS_DIR / "tray.log"
logging.basicConfig(
    filename=str(TRAY_LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("marketdata.tray")

# Windows Registry & App Constants
STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "MarketDataTray"
MUTEX_NAME = "MarketData_Tray_SingleInstance_Mutex"


# ---------------------------------------------------------------------------
# Native Windows Single-Instance Mutex & Clipboard Utilities
# ---------------------------------------------------------------------------

def acquire_single_instance_mutex() -> Optional[int]:
    """Ensures only one instance of the tray app runs at a time."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.GetLastError.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        if mutex:
            kernel32.CloseHandle(ctypes.c_void_p(mutex))
        return None
    return mutex


def copy_to_clipboard(text: str) -> bool:
    """Copies text to the Windows system clipboard using the Win32 API."""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.EmptyClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.restype = ctypes.c_bool

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        for _ in range(5):  # Retry up to 5 times if clipboard is briefly held
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    encoded = (text + "\0").encode("utf-16le")
                    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                    if not h_mem:
                        return False
                    p_mem = kernel32.GlobalLock(h_mem)
                    if not p_mem:
                        kernel32.GlobalFree(h_mem)
                        return False
                    ctypes.cdll.msvcrt.memcpy(ctypes.c_void_p(p_mem), encoded, len(encoded))
                    kernel32.GlobalUnlock(h_mem)
                    user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                    return True
                finally:
                    user32.CloseClipboard()
            time.sleep(0.05)
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# Windows Startup Manager (HKCU\Software\Microsoft\Windows\CurrentVersion\Run)
# ---------------------------------------------------------------------------

def get_startup_command() -> str:
    """Returns the windowless pythonw startup command string."""
    python_exe = Path(sys.executable)
    # Prefer pythonw.exe to prevent any console window popup on boot
    pythonw_exe = python_exe.parent / "pythonw.exe"
    target_py = str(pythonw_exe) if pythonw_exe.exists() else str(python_exe)
    
    # Launch tray module directly
    return f'"{target_py}" -m marketdata.tray'


def is_startup_enabled() -> bool:
    """Checks whether MarketDataTray is configured to run at Windows login."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def enable_startup() -> bool:
    """Registers MarketDataTray in HKCU Run registry."""
    try:
        cmd = get_startup_command()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        return True
    except Exception as e:
        print(f"Failed to enable startup: {e}")
        return False


def disable_startup() -> bool:
    """Removes MarketDataTray from HKCU Run registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        print(f"Failed to disable startup: {e}")
        return False


def toggle_startup() -> bool:
    """Toggles startup status and returns new state."""
    if is_startup_enabled():
        disable_startup()
        return False
    else:
        enable_startup()
        return True


# ---------------------------------------------------------------------------
# High-DPI Dynamic Icon Generation
# ---------------------------------------------------------------------------

def create_tray_icon_image(state: str = "idle") -> Image.Image:
    """
    Renders a crisp 64x64 icon representing financial candlestick chart + market pulse.
    States: 'idle', 'syncing', 'success', 'error'
    """
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Base rounded background container
    bg_color = (22, 27, 34, 240)  # Modern dark slate
    draw.rounded_rectangle([4, 4, size - 4, size - 4], radius=14, fill=bg_color, outline=(48, 54, 61, 255), width=2)

    # Financial Candlestick Bars
    # Candle 1 (Bullish green)
    draw.line([(18, 14), (18, 48)], fill=(46, 160, 67, 255), width=2)  # Wick
    draw.rounded_rectangle([13, 22, 23, 42], radius=2, fill=(46, 160, 67, 255))

    # Candle 2 (Bearish red/orange or subtle)
    draw.line([(32, 20), (32, 52)], fill=(248, 81, 73, 255), width=2)  # Wick
    draw.rounded_rectangle([27, 28, 37, 46], radius=2, fill=(248, 81, 73, 255))

    # Candle 3 (Bullish vibrant cyan/green)
    draw.line([(46, 10), (46, 44)], fill=(56, 189, 248, 255), width=2)  # Wick
    draw.rounded_rectangle([41, 16, 51, 36], radius=2, fill=(56, 189, 248, 255))

    # Status Badge / Indicator
    if state == "syncing":
        # Animated golden/amber pulse circle
        draw.ellipse([42, 42, 58, 58], fill=(234, 179, 8, 255), outline=(22, 27, 34, 255), width=2)
        # Inner sync dot
        draw.ellipse([47, 47, 53, 53], fill=(255, 255, 255, 255))
    elif state == "success":
        # Vibrant green check indicator
        draw.ellipse([44, 44, 58, 58], fill=(34, 197, 94, 255), outline=(22, 27, 34, 255), width=2)
    elif state == "error":
        # Red error badge
        draw.ellipse([44, 44, 58, 58], fill=(239, 68, 68, 255), outline=(22, 27, 34, 255), width=2)
    else:
        # Subtle idle glowing dot
        draw.ellipse([46, 46, 56, 56], fill=(59, 130, 246, 255))

    return image


# (Data Availability Explorer GUI removed — menu-only tray per spec.)


def _patch_pystray_left_click(icon) -> None:
    """Make left-click open the native context menu, Tailscale-style.

    pystray's Win32 backend opens the popup menu only on right-click; left-click
    instead activates the menu's default item. We removed that default item, so
    reroute left-click to the same popup path. If pystray's internals change,
    fall back to today's right-click-only behavior.
    """
    try:
        import pystray._win32 as _win32_mod
        win32 = _win32_mod.win32
        handlers = icon._message_handlers
        original = handlers[win32.WM_NOTIFY]

        def _on_notify(wparam, lparam):
            if lparam in (win32.WM_LBUTTONUP, win32.WM_RBUTTONUP):
                lparam = win32.WM_RBUTTONUP
            return original(wparam, lparam)

        handlers[win32.WM_NOTIFY] = _on_notify
    except Exception as e:  # pragma: no cover - depends on pystray internals
        logger.warning("Could not enable left-click tray menu; right-click only. %s", e)


# ---------------------------------------------------------------------------
# Tray Application Controller & Menu Engine
# ---------------------------------------------------------------------------

class MarketDataTrayApp:
    """Manages the background system tray icon, notifications, sync engine, and timers."""

    def __init__(self):
        self.icon: Optional[pystray.Icon] = None
        self.is_syncing = False
        self.last_sync_time: Optional[datetime.datetime] = None
        self.last_sync_report: Optional[SyncReport] = None
        self.last_sync_summary: str = "No sync performed yet"
        
        # Load user preference for auto-sync interval
        cfg = get_user_config()
        self.auto_sync_interval: int = int(cfg.get("auto_sync_interval", 3600))  # Default 1 hour
        self.auto_sync_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

    def get_status_label(self) -> str:
        """Returns the real-time status label for the top menu row."""
        if self.is_syncing:
            return "Status: Syncing in progress..."
        if self.last_sync_time:
            time_str = self.last_sync_time.strftime("%H:%M:%S")
            return f"Status: Idle (Last: {time_str})"
        return "Status: Idle (No sync yet)"

    def get_last_sync_label(self) -> str:
        """Returns compact sync performance info."""
        if not self.last_sync_report:
            return "Last Sync: None"
        r = self.last_sync_report
        return f"Last Sync: +{r.total_bars_added:,} bars, {r.updated_count} updated ({r.duration_seconds:.1f}s)"

    def notify(self, title: str, message: str):
        """Displays a native Windows tray balloon/toast notification."""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def perform_sync(
        self,
        categories: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        force: bool = False,
    ):
        """Asynchronously executes the delta sync in a worker thread."""
        if self.is_syncing:
            self.notify("MarketData Sync", "A synchronization is already running in background.")
            return

        def _worker():
            self.is_syncing = True
            if self.icon:
                self.icon.icon = create_tray_icon_image("syncing")
                self.icon.title = "MarketData - Syncing in progress..."
                self.icon.update_menu()

            try:
                engine = CronSyncEngine()
                report = engine.sync(
                    categories=categories,
                    timeframes=timeframes or ["1h"],
                    check_market_hours=not force,
                    force=force,
                )
                self.last_sync_report = report
                self.last_sync_time = datetime.datetime.now()
                
                msg = f"Updated {report.updated_count} series (+{report.total_bars_added:,} bars) in {report.duration_seconds:.1f}s"
                if report.error_count > 0:
                    msg += f" with {report.error_count} error(s)"
                self.last_sync_summary = msg

                self.notify("MarketData Sync Completed", msg)
            except Exception as e:
                self.last_sync_summary = f"Sync failed: {e}"
                self.notify("MarketData Sync Error", str(e))
            finally:
                self.is_syncing = False
                if self.icon:
                    self.icon.icon = create_tray_icon_image("idle")
                    self.icon.title = f"MarketData - {self.get_last_sync_label()}"
                    self.icon.update_menu()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def copy_data_path_action(self):
        """Copies active data folder path to clipboard and notifies."""
        data_path = str(DATA_DIR.resolve())
        success = copy_to_clipboard(data_path)
        if success:
            self.notify("Copied to Clipboard", f"Market Data Path:\n{data_path}")
        else:
            self.notify("Clipboard Error", "Unable to copy path to clipboard.")

    def copy_base_path_action(self):
        """Copies project/home base folder path to clipboard."""
        base_path = str(BASE_DIR.resolve())
        copy_to_clipboard(base_path)
        self.notify("Copied to Clipboard", f"Home Directory:\n{base_path}")

    def open_data_folder(self):
        """Reveals data folder in Windows File Explorer."""
        subprocess.run(["explorer", str(DATA_DIR)])

    def toggle_startup_action(self):
        """Toggles Windows startup and notifies."""
        is_now_on = toggle_startup()
        if is_now_on:
            self.notify("Startup Configured", "MarketData tray will automatically start on Windows boot.")
        else:
            self.notify("Startup Removed", "MarketData tray will no longer start on boot.")
        if self.icon:
            self.icon.update_menu()

    def set_auto_sync_interval(self, seconds: int):
        """Updates auto-sync frequency."""
        self.auto_sync_interval = seconds
        set_user_config_value("auto_sync_interval", seconds)
        if seconds == 0:
            self.notify("Auto-Sync Disabled", "Automatic background syncing is paused.")
        else:
            mins = seconds // 60
            self.notify("Auto-Sync Updated", f"Background sync interval set to every {mins} minutes.")
        if self.icon:
            self.icon.update_menu()

    def auto_sync_loop(self):
        """Background daemon thread that runs periodic incremental delta sync."""
        while not self.stop_event.is_set():
            if self.auto_sync_interval > 0:
                # Count elapsed seconds
                for _ in range(self.auto_sync_interval):
                    if self.stop_event.is_set() or self.auto_sync_interval == 0:
                        break
                    time.sleep(1)

                if not self.stop_event.is_set() and self.auto_sync_interval > 0:
                    self.perform_sync(timeframes=["1h"], force=False)
            else:
                time.sleep(5)

    def create_menu(self) -> Menu:
        """Constructs the dynamic system tray context menu."""
        return Menu(
            # Status header (informational, non-interactive)
            MenuItem(lambda item: self.get_status_label(), action=None, enabled=False),
            MenuItem(lambda item: f"   {self.get_last_sync_label()}", action=None, enabled=False),
            Menu.SEPARATOR,

            # Sync Trigger Sub-Menu
            MenuItem(
                "Sync Data Now",
                Menu(
                    MenuItem("Sync Hourly Active [1h]", lambda icon, item: self.perform_sync(timeframes=["1h"])),
                    MenuItem("Sync Daily [1d]", lambda icon, item: self.perform_sync(timeframes=["1d"])),
                    MenuItem("Sync All Timeframes [1m - 1d]", lambda icon, item: self.perform_sync(timeframes=["1d", "1h", "30m", "15m", "5m", "1m"])),
                    Menu.SEPARATOR,
                    MenuItem("Force Full Refresh (Ignore Hours)", lambda icon, item: self.perform_sync(timeframes=["1h"], force=True)),
                ),
            ),

            Menu.SEPARATOR,

            # Clipboard & Folder Access
            MenuItem("Copy Market Data Path", lambda icon, item: self.copy_data_path_action()),
            MenuItem("Open Data Folder in Explorer", lambda icon, item: self.open_data_folder()),
            Menu.SEPARATOR,

            # Windows Startup & Scheduler Settings
            MenuItem(
                "Run on Windows Startup",
                action=lambda icon, item: self.toggle_startup_action(),
                checked=lambda item: is_startup_enabled(),
            ),
            MenuItem(
                "Auto-Sync Interval",
                Menu(
                    MenuItem("Disabled", lambda icon, item: self.set_auto_sync_interval(0), checked=lambda item: self.auto_sync_interval == 0),
                    MenuItem("Every 15 Minutes", lambda icon, item: self.set_auto_sync_interval(900), checked=lambda item: self.auto_sync_interval == 900),
                    MenuItem("Every 1 Hour (Default)", lambda icon, item: self.set_auto_sync_interval(3600), checked=lambda item: self.auto_sync_interval == 3600),
                    MenuItem("Every 4 Hours", lambda icon, item: self.set_auto_sync_interval(14400), checked=lambda item: self.auto_sync_interval == 14400),
                    MenuItem("Every 24 Hours", lambda icon, item: self.set_auto_sync_interval(86400), checked=lambda item: self.auto_sync_interval == 86400),
                ),
            ),
            Menu.SEPARATOR,

            # Exit
            MenuItem("Exit MarketData Tray", lambda icon, item: self.quit()),
        )

    def quit(self):
        """Stops threads and removes tray icon cleanly."""
        self.stop_event.set()
        if self.icon:
            self.icon.stop()

    def run(self):
        """Starts background daemon and runs tray loop."""
        if not HAS_PYSTRAY:
            logger.error("'pystray' and 'pillow' are required to run the tray application.")
            print("Error: 'pystray' and 'pillow' are required to run the tray application.")
            sys.exit(1)

        logger.info("Initializing MarketData Tray Application...")

        # Start auto-sync worker
        self.auto_sync_thread = threading.Thread(target=self.auto_sync_loop, daemon=True)
        self.auto_sync_thread.start()

        # Build pystray icon
        icon_img = create_tray_icon_image("idle")
        self.icon = Icon(
            name="MarketData",
            icon=icon_img,
            title="MarketData - Universal Historical Data Downloader",
            menu=self.create_menu(),
        )

        # Tailscale-style: left-click opens the same native menu as right-click.
        _patch_pystray_left_click(self.icon)

        def on_ready(icon):
            icon.visible = True
            startup_status = "enabled" if is_startup_enabled() else "disabled"
            logger.info("MarketData Tray is ready in Windows notification area.")
            try:
                icon.notify(
                    f"Active data path: {DATA_DIR}\nStartup on boot: {startup_status}",
                    "MarketData Background Tray Running",
                )
            except Exception as e:
                logger.warning(f"Could not display initial notification balloon: {e}")

        # Main blocking tray loop
        self.icon.run(setup=on_ready)


# ---------------------------------------------------------------------------
# CLI Command Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MarketData Windows System Tray Popup Application")
    parser.add_argument("--install-startup", action="store_true", help="Enable MarketData tray to run on Windows startup and exit")
    parser.add_argument("--remove-startup", action="store_true", help="Disable MarketData tray from running on Windows startup and exit")
    parser.add_argument("--status", action="store_true", help="Print current startup registration status and exit")
    args = parser.parse_args()

    if args.install_startup:
        if enable_startup():
            print("Successfully registered MarketData Tray in Windows startup (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).")
            print(f"Command: {get_startup_command()}")
        else:
            print("Failed to register in Windows startup.")
        return

    if args.remove_startup:
        if disable_startup():
            print("Successfully removed MarketData Tray from Windows startup.")
        else:
            print("Failed to remove from Windows startup.")
        return

    if args.status:
        enabled = is_startup_enabled()
        print(f"Windows Startup Enabled: {enabled}")
        print(f"Startup Command:         {get_startup_command()}")
        print(f"Active Data Directory:   {DATA_DIR}")
        return

    # Single-instance check
    mutex = acquire_single_instance_mutex()
    if not mutex:
        logger.warning("Another instance of MarketData Tray is already running.")
        print("MarketData Tray is already running in the Windows notification area.")
        return

    app = MarketDataTrayApp()
    try:
        app.run()
    except Exception as e:
        logger.exception(f"Unhandled error in tray app: {e}")
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
