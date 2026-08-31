# Design: Tailscale-style Native Tray Menu (no tkinter)

**Date:** 2026-08-31
**Status:** Approved

## Goal

Make `marketdata`'s Windows system tray behave like Tailscale's: clicking the tray
icon (left- or right-click) opens a small, native Windows context menu with the
action options — not a full tkinter window. Remove all `tkinter` usage from the tray
code path.

## Problem

Today the tray already renders a native Win32 context menu via `pystray` on
**right-click**. Two issues:

1. The menu marks *"Explore Data Availability…"* as `default=True`. On **left-click**
   pystray activates that default item, which opens a full 880×560 tkinter table GUI.
   This is the "full tkinter window" the user sees on click.
2. `tkinter` is used in four places in `marketdata/tray.py`: the big Data
   Availability Explorer table, a `messagebox` for last-sync details,
   `--explore` CLI handling, and a clipboard fallback.

## Decision (user-approved)

- **Menu-only**: drop the Data Availability Explorer table and the sync-details
  popup entirely. Everything lives in the small native menu.
- **Approach**: keep `pystray` (native menu, notifications, high-DPI already
  handled) and add a small patch so a left-click opens the same popup menu as a
  right-click, instead of activating the default item.

## Changes

### `marketdata/tray.py`

1. **Left-click opens the native menu.** Add `_patch_pystray_left_click(icon)`.
   pystray (`_win32.py`) dispatches `WM_NOTIFY` to `self._on_notify`; the
   `_on_notify` method calls `self()` on `WM_LBUTTONUP` (activates the default
   item) or shows `TrackPopupMenu` on `WM_RBUTTONUP`. Because the dispatch is via
   instance-attribute lookup, we override the instance's `_on_notify` so that
   `WM_LBUTTONUP`, `WM_LBUTTONDBLCLK`, and `WM_RBUTTONUP` all route to the existing
   popup path. Wrap defensively in try/except: if pystray internals change, degrade
   to today's right-click-only behavior (menu still present) and log a warning.

2. **Remove all tkinter:**
   - Delete `show_data_explorer()`, `_run_explorer_gui()`, and the module globals
     `_explorer_window`, `_explorer_lock`.
   - Delete `show_sync_details()` (tkinter messagebox). Status and last-sync info
     remain as the top rows of the menu.
   - Remove the tkinter fallback block in `copy_to_clipboard()` (the Win32 primary
     path already succeeds).
   - Remove `--explore` handling in `main()` and its `_run_explorer_gui` reference.

3. **Menu cleanup:** drop `default=True` and the *"Explore Data Availability…"* /
   `Cached Data:` rows. Keep: status rows, Sync Data Now submenu, Copy Market Data
   Path, Open Data Folder, Run on Windows Startup (checked), Auto-Sync Interval
   submenu, Exit MarketData Tray.

### `marketdata/cli.py`

- Remove the `--explore` flag definition (around line 848).
- Remove the `if args.explore: show_data_explorer()` block and the
  `show_data_explorer` import in `cmd_tray`.

### Docs

- `AGENTS.md` line 62: remove `marketdata tray --explore`.
- `readme.md` lines 139 and 157–158: remove the Data Availability Explorer GUI
  bullet and the `--explore` example.

### Tests

- `tests/test_tray.py` only references non-tkinter functions and should pass
  unchanged.
- Add one regression guard in `tests/test_tray.py`: read `marketdata/tray.py`
  source and assert the string `tkinter` does not appear (after the change it
  has zero occurrences). This is deterministic regardless of where an import is
  scoped.

## Non-Changes

- No new runtime dependencies. `pystray` and `pillow` remain.
- The native Win32 clipboard, mutex, and registry helpers are unchanged.
- The auto-sync daemon and sync submenu behavior are unchanged.

## Verification

- `marketdata tray --status` exits cleanly.
- Unit tests (`tests/test_tray.py`) pass.
- The left-click-opens-menu behavior depends on the live Win32 message loop and
  cannot be exercised headlessly from this shell; it requires a real tray session.
  This will be flagged in the plan.

## Open Questions

None.