"""Unit and integration tests for MarketData Windows System Tray popup."""

from pathlib import Path
import unittest
from PIL import Image

from marketdata.tray import (
    create_tray_icon_image,
    copy_to_clipboard,
    get_startup_command,
    is_startup_enabled,
    enable_startup,
    disable_startup,
    toggle_startup,
    MarketDataTrayApp,
)


class TestMarketDataTray(unittest.TestCase):
    def test_tray_icon_generation(self):
        """Verify that dynamic PIL icon images render with expected sizes and modes."""
        for state in ["idle", "syncing", "success", "error"]:
            img = create_tray_icon_image(state)
            self.assertIsInstance(img, Image.Image)
            self.assertEqual(img.size, (64, 64))
            self.assertEqual(img.mode, "RGBA")

    def test_startup_command_format(self):
        """Verify startup command references pythonw.exe and module."""
        cmd = get_startup_command()
        self.assertIn("marketdata.tray", cmd)
        self.assertIn("python", cmd.lower())

    def test_startup_registry_toggle(self):
        """Verify enabling, querying, and disabling Windows HKCU startup registry key."""
        # Ensure starting clean
        disable_startup()
        self.assertFalse(is_startup_enabled())

        # Enable
        success = enable_startup()
        self.assertTrue(success)
        self.assertTrue(is_startup_enabled())

        # Toggle to disabled
        new_state = toggle_startup()
        self.assertFalse(new_state)
        self.assertFalse(is_startup_enabled())

        # Clean up (ensure disabled)
        disable_startup()
        self.assertFalse(is_startup_enabled())

    def test_clipboard_copy(self):
        """Verify Win32 clipboard writer works without exception."""
        test_text = "C:\\Users\\Test\\Data\\marketdata"
        result = copy_to_clipboard(test_text)
        self.assertTrue(result)

    def test_tray_app_initialization(self):
        """Verify tray application object initializes with default settings."""
        app = MarketDataTrayApp()
        self.assertFalse(app.is_syncing)
        self.assertIn("Idle", app.get_status_label())
        self.assertIn("None", app.get_last_sync_label())
        
        # Test menu creation
        menu = app.create_menu()
        self.assertIsNotNone(menu)


class _FakeMessageHandlersIcon:
    """Minimal stand-in for pystray.Icon exposing its _message_handlers dict."""

    def __init__(self):
        import pystray._win32 as _win32_mod
        self._win32 = _win32_mod.win32
        self._message_handlers = {self._win32.WM_NOTIFY: self._on_notify}

    def _on_notify(self, wparam, lparam):
        return (wparam, lparam)


class TestPystrayLeftClickPatch(unittest.TestCase):
    def test_left_click_routes_to_popup(self):
        import pystray._win32 as _win32_mod
        from marketdata.tray import _patch_pystray_left_click
        win32 = _win32_mod.win32
        icon = _FakeMessageHandlersIcon()
        handler = icon._message_handlers[win32.WM_NOTIFY]

        # Before the patch, left-click keeps its own message (activates default).
        self.assertEqual(handler(0, win32.WM_LBUTTONUP), (0, win32.WM_LBUTTONUP))

        _patch_pystray_left_click(icon)
        handler = icon._message_handlers[win32.WM_NOTIFY]

        # After the patch, left-click is rerouted to the popup (right-click) path.
        self.assertEqual(handler(0, win32.WM_LBUTTONUP), (0, win32.WM_RBUTTONUP))
        # Right-click still maps to itself.
        self.assertEqual(handler(0, win32.WM_RBUTTONUP), (0, win32.WM_RBUTTONUP))
        # Unrelated messages pass through untouched.
        self.assertEqual(handler(0, 0x0300), (0, 0x0300))


if __name__ == "__main__":
    unittest.main()
