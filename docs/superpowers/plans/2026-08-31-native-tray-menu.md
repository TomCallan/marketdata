# Tailscale-style Native Tray Menu (no tkinter) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `marketdata` Windows tray icon open a native Windows context menu on left- or right-click (like Tailscale) and remove every `tkinter` usage from the tray code path.

**Architecture:** Keep the existing `pystray` tray (native Win32 menu, notifications, high-DPI). Override the icon's `_message_handlers[WM_NOTIFY]` entry so left-click routes to the same `TrackPopupMenu` path as right-click. Strip all tkinter code (Data Explorer table, sync-details messagebox, clipboard fallback, `--explore`) from `marketdata/tray.py` and `marketdata/cli.py`, and refresh the docs.

**Tech Stack:** Python 3.10+, `pystray` (Win32 backend), `Pillow`, `ctypes` (unchanged). No new dependencies. No `tkinter`.

## Global Constraints

- No `tkinter` import may appear anywhere in `marketdata/tray.py` after implementation (enforced by a regression test).
- No new runtime dependencies. `pystray` and `Pillow` already in `pyproject.toml` stay; nothing added.
- Windows-only code already in this file (`winreg`, `ctypes.windll`) is unchanged.
- Follow the approved spec: `docs/superpowers/specs/2026-08-31-native-tray-menu-design.md`.
- Tests run from the repo venv: `.venv/Scripts/python.exe` (Windows). Use `unittest` (the existing `tests/test_tray.py` style).
- The user has authorized git commits; commit after each task.

---

### Task 1: Left-click opens the native menu (patch + route test)

**Files:**
- Modify: `marketdata/tray.py` — add new module-level function `_patch_pystray_left_click`; call it in `MarketDataTrayApp.run()`.
- Test: `tests/test_tray.py` — add `_FakeMessageHandlersIcon` and `test_pystray_left_click_patch`.

**Interfaces:**
- Consumes: nothing new (uses the existing `logger` and `Handler`-agnostic `icon._message_handlers` dict).
- Produces: `_patch_pystray_left_click(icon) -> None` — idempotently replaces `icon._message_handlers[WM_NOTIFY]` so `WM_LBUTTONUP` and `WM_RBUTTONUP` both call the original right-click (popup) path.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tray.py` (after the existing `TestMarketDataTray` class):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m unittest tests.test_tray.TestPystrayLeftClickPatch -v`
Expected: FAIL with `ImportError: cannot import name '_patch_pystray_left_click'`.

- [ ] **Step 3: Write minimal implementation**

Add this function to `marketdata/tray.py`, directly above the `class MarketDataTrayApp:` definition (after the `create_tray_icon_image` function):

```python
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
```

Then wire it in `MarketDataTrayApp.run()`. Locate `self.icon = Icon(name="MarketData", ...)` inside `run()` and insert the patch call directly below it (before `def on_ready(icon):`):

```python
        self.icon = Icon(
            name="MarketData",
            icon=icon_img,
            title="MarketData - Universal Historical Data Downloader",
            menu=self.create_menu(),
        )

        # Tailscale-style: left-click opens the same native menu as right-click.
        _patch_pystray_left_click(self.icon)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_tray.TestPystrayLeftClickPatch -v`
Expected: PASS (3 assertions).

- [ ] **Step 5: Commit**

```bash
git add marketdata/tray.py tests/test_tray.py docs/superpowers/specs/2026-08-31-native-tray-menu-design.md docs/superpowers/plans/2026-08-31-native-tray-menu.md
git commit -m "feat(tray): open native menu on left-click, Tailscale-style"
```

---

### Task 2: Remove tkinter Data Explorer, sync-details popup, clipboard fallback, and `--explore` from tray.py

**Files:**
- Modify: `marketdata/tray.py`

**Interfaces:**
- Consumes: nothing (deletions only + one `Menu` tweak).
- Produces: `marketdata/tray.py` free of any `tkinter` import or reference; `main()` no longer defines a `--explore` flag; clipboard still returns `bool` via Win32.

- [ ] **Step 1: Confirm the current baseline passes**

Run: `.venv/Scripts/python.exe -m unittest tests.test_tray -v`
Expected: All existing tests PASS (they do not use the removed features).

- [ ] **Step 2: Remove the Data Availability Explorer GUI block**

In `marketdata/tray.py`, delete the entire section from the comment on line 252
(`# Data Availability Explorer Window (Lightweight Tkinter GUI)`) through the end
of `_run_explorer_gui()` on line 562 (the `root.mainloop()` block), inclusive of
the `_explorer_window`, `_explorer_lock`, `show_data_explorer`, and
`_run_explorer_gui` definitions. Replace that whole span with a single comment:

```python
# (Data Availability Explorer GUI removed — menu-only tray per spec.)
```

- [ ] **Step 3: Remove `show_sync_details`**

Delete the method `show_sync_details(self):` (lines ~668–693), which uses
`tkinter`. The status rows in the menu (Task 5) are made non-interactive, so no
caller remains.

- [ ] **Step 4: Remove the tkinter clipboard fallback**

In `copy_to_clipboard`, change the docstring and drop the fallback. Replace:

```python
    """Copies text to the Windows system clipboard using Win32 API with Tkinter fallback."""
```

with:

```python
    """Copies text to the Windows system clipboard using the Win32 API."""
```

Then replace the entire tail of the function (the `# Tkinter fallback` block from
`    # Tkinter fallback` through its final `        return False`):

```python
    # Tkinter fallback
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False
```

with a single Win32-exit fallback:

```python
    return False
```

- [ ] **Step 5: Remove `--explore` handling from `main()`**

Delete the argparse argument on line 864:

```python
    parser.add_argument("--explore", action="store_true", help="Launch the Data Availability Explorer GUI directly")
```

Delete the handler block (lines ~889–891):

```python
    if args.explore:
        _run_explorer_gui()
        return
```

- [ ] **Step 6: Remove the `Cached Data` / Explorer rows and de-`default` the menu**

In `create_menu()`, delete these two `MenuItem`s (lines ~780–781):

```python
            MenuItem("Explore Data Availability...", lambda icon, item: show_data_explorer(), default=True),
            MenuItem(lambda item: f"   {self.get_cache_summary_label()}", lambda icon, item: show_data_explorer()),
```

Delete the now-unused `get_cache_summary_label` method (lines ~601–610).

- [ ] **Step 7: Update the module docstring**

Replace the docstring bullet (line 7): `- Visual Data Availability & Cache Explorer GUI`
with:
`- Native Windows context menu on left- or right-click (menu-only, no GUI windows)`

- [ ] **Step 8: Run the tests**

Run: `.venv/Scripts/python.exe -m unittest tests.test_tray -v`
Expected: PASS (including the Task 1 patch test).

- [ ] **Step 9: Commit**

```bash
git add marketdata/tray.py
git commit -m "refactor(tray): remove all tkinter, drop heavy GUI to be menu-only"
```

---

### Task 3: Remove `--explore` from the CLI

**Files:**
- Modify: `marketdata/cli.py`

**Interfaces:**
- Consumes: none.
- Produces: `marketdata tray --help` no longer lists `--explore`; `cmd_tray` no longer imports or calls `show_data_explorer`.

- [ ] **Step 1: Remove the flag and import**

In `marketdata/cli.py`:
- Delete `show_data_explorer,` from the `from marketdata.tray import (...)` block in `cmd_tray` (line ~694).
- Delete the `if args.explore:` block (lines ~734–736):

```python
    if args.explore:
        show_data_explorer()
        return
```

- Delete the argparse `--explore` argument in `build_parser` (line ~848):

```python
    p_tray.add_argument("--explore", action="store_true", help="Launch the Data Availability Explorer GUI directly")
```

- [ ] **Step 2: Verify the CLI**

Run: `.venv/Scripts/python.exe -m marketdata tray --help`
Expected: `usage: ...` shows `--install-startup`, `--remove-startup`, `--status` and **no** `--explore`. Exit code 0.

- [ ] **Step 3: Commit**

```bash
git add marketdata/cli.py
git commit -m "feat(cli): drop tray --explore flag"
```

---

### Task 4: Update docs (AGENTS.md, readme.md)

**Files:**
- Modify: `AGENTS.md`, `readme.md`

- [ ] **Step 1: `AGENTS.md`**

Remove the line `marketdata tray --explore` (line 62) so the tray bullet only shows the supported commands.

- [ ] **Step 2: `readme.md`**

- Remove the bullet on line 139: `- **Visual Data Availability Explorer**: Sleek GUI table with live search & category filters to inspect all cached Parquet datasets, row counts, disk usage, and open directly in Windows File Explorer.`
- Remove the `# Launch the visual Data Availability Explorer directly` heading and the `marketdata tray --explore` line (lines 157–158).

- [ ] **Step 3: Self-check**

Run: `git diff -- AGENTS.md readme.md`
Expected: only the lines above are removed; no other content touched.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md readme.md
git commit -m "docs: remove Data Availability Explorer references"
```

---

### Task 5: Add the no-tkinter regression guard + full suite

**Files:**
- Modify: `tests/test_tray.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: a deterministic guard that fails the build if `tkinter` ever returns to `marketdata/tray.py`.

- [ ] **Step 1: Write the test**

Append to `tests/test_tray.py` (a new standalone function or method inside `TestMarketDataTray`):

```python
    def test_tray_source_has_no_tkinter(self):
        """Guard: the tray must never import tkinter."""
        tray_path = Path(__file__).resolve().parent.parent / "marketdata" / "tray.py"
        source = tray_path.read_text(encoding="utf-8")
        self.assertNotIn("tkinter", source)
```

- [ ] **Step 2: Run the full suite**

Run: `.venv/Scripts/python.exe -m unittest tests.test_tray tests.test_data_pipeline -v`
Expected: PASS. (If `test_data_pipeline` already fails on a clean baseline unrelated to this change, that is a pre-existing condition — report it rather than "fixing" it.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_tray.py
git commit -m "test(tray): guard against reintroducing tkinter"
```

---

### Task 6: Final verification

- [ ] **Step 1: Import smoke test**

Run: `.venv/Scripts/python.exe -c "import marketdata.tray as t; print('ok', t._patch_pystray_left_click); print('explorer removed', not hasattr(t, 'show_data_explorer'))"`
Expected: `ok <function _patch_pystray_left_click ...>` and `explorer removed True`.

- [ ] **Step 2: Tray startup status (no GUI)**

Run: `.venv/Scripts/python.exe -m marketdata.tray --status`
Expected: prints `Windows Startup Enabled: ...` and exits (no window, no error).

- [ ] **Step 3: Live behavior note**

The left-click-opens-menu behavior runs inside pystray's Win32 message loop and
cannot be exercised headlessly. Report to the user that they should start the tray
(`.venv\Scripts\pythonw.exe -m marketdata.tray` or the `.bat`) once and confirm that
both left- and right-click open the native menu. Do not claim this was verified
headlessly.

- [ ] **Step 4: Confirm git state**

Run: `git status --short`
Expected: working tree clean (all changes committed across Tasks 1–5). If anything is
uncommitted, add and commit it in one final commit:
`git add -A && git commit -m "chore: commit remaining tray changes"`.

---

## Self-Review

**Spec coverage:**
- Left-click opens native menu → Task 1. ✔
- Remove tkinter Explorer table → Task 2. ✔
- Remove sync-details tkinter popup → Task 2. ✔
- Remove tkinter clipboard fallback → Task 2. ✔
- Remove `--explore` (tray.py `main()` + cli.py) → Tasks 2 & 3. ✔
- Remove `default=True` and Explorer/Cached rows → Task 2. ✔
- Docs (AGENTS.md, readme.md) → Task 4. ✔
- Regression guard → Task 5. ✔
- Verification incl. live-behavior caveat → Task 6. ✔

**Placeholder scan:** All steps carry concrete code or exact commands; no TBD/TODO.

**Type consistency:** `_patch_pystray_left_click(icon)` is defined in Task 1 (Step 3) and referenced by Task 1 test, Task 6 smoke test. `show_data_explorer` is removed in Task 2 before cli.py stops importing it in Task 3 — order is safe. `get_cache_summary_label` removed in Task 2 with its only menu caller. Consistent.