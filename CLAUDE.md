# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A cross-platform (Linux/Windows/macOS) touchscreen kiosk UI for the ZKETECH
EBC-A20 battery capacity tester, written in Python + Tkinter. Targets are as
small as a Raspberry Pi Zero touchscreen, hence Tkinter over anything
GPU/OpenGL-dependent.

The EBC-A20 has no official protocol documentation - the serial driver
(`ebc/protocol.py`, `ebc/device.py`) is reverse-engineered from two public
write-ups that agree on framing/checksum/encoding but disagree on serial
parity and have some fields still unverified against real hardware. Read
the module docstring at the top of `ebc/protocol.py` before touching
anything in the device I/O path - it documents exactly what's confirmed
against real hardware vs. still unverified, and getting it wrong risks
mis-displaying live current/voltage during an actual charge/discharge.

## Commands

Run from source (any OS):
```bash
pip install -r requirements.txt
python main.py
```
Tkinter itself isn't a pip package - on Debian/Ubuntu install it separately
with `sudo apt install python3-tk`.

There is no test suite, linter, or type-checker configured in this repo.

Run the UI in a container with its window forwarded to your X server
(avoids installing `python3-tk`/`pyserial` locally):
```bash
bash deploy/test-local-ui.sh              # normal windowed mode
bash deploy/test-local-ui.sh --kiosk      # fullscreen/no-cursor kiosk preview
```
Offers to pass through a real EBC-A20's `/dev/ttyUSB*`/`/dev/ttyACM*` device
if one is plugged in; otherwise use the in-app simulator.

Build the source-package tarball (also stamps `ui/build_info.py`, which is a
dirtying side effect on your working copy - `git checkout -- ui/build_info.py`
after if unwanted):
```bash
bash deploy/build-package.sh [version]   # defaults to `git describe --tags --always`
```

Reproduce the CI Flatpak build locally (iterate on packaging failures
without a CI round-trip; needs `flatpak`/`flatpak-builder` installed, no
Docker/systemd workaround required):
```bash
bash deploy/build-flatpak-local.sh          # build, then run it
bash deploy/build-flatpak-local.sh --build  # build only
```
Builds `flatpak/io.github.deeja.BatteryTesterKiosk.yml` - the same manifest
CI uses. Leaves `flatpak/builddir` and `flatpak/.flatpak-builder` (gitignored)
- rerun freely, or `rm -rf flatpak/builddir flatpak/.flatpak-builder` to
start clean.

All of the above are also wired up as VS Code tasks (`.vscode/tasks.json`).

Releases are cut by pushing a `v*` tag - `.github/workflows/release.yml` then
builds the source tarball, Flatpak (x86_64/aarch64, QEMU-emulated for
aarch64), Windows `.exe` (PyInstaller), and macOS `.app` (PyInstaller) in
parallel and attaches them all to one GitHub release.

## Architecture

**`ebc/`** - hardware/protocol layer, no UI dependencies.
- `protocol.py` - wire format: frame markers, checksum, base-240 value
  encoding, status codes. Pure functions/dataclasses, no I/O.
- `device.py` (`EbcDevice`) - real serial device. All I/O runs on a
  background thread; decoded `Sample`s and raw `RawFrame`s are handed to the
  UI via two `queue.Queue`s, polled from Tk's main loop (never touch Tk
  widgets from this thread).
- `mock_device.py` (`MockEbcDevice`) - same interface as `EbcDevice`
  (`connect`/`disconnect`/`start_*`/`stop`/`sample_queue`/`raw_queue`),
  simulating plausible CC/CP/CV curves. This is what "Use Simulator" wires
  up, and also what runs on a dev machine when the app is asked to talk to
  `SIM (no hardware)`. Keep this interface in sync with `EbcDevice` - the UI
  code doesn't distinguish between the two.
- `sequencer.py` (`AutoCycleController`) - Repeat-mode (Charge→rest→
  Discharge→rest, looped) orchestration. Not its own thread: driven by
  `MainScreen`'s existing poll loop (`on_sample()` for status transitions,
  `tick()` for rest-timer countdowns), so it shares the Tk main thread and
  needs no locking. Exists because the device has no confirmed wire command
  for a native multi-cycle Auto test.
- `config.py` (`TestConfig`) - the single active test configuration, shared
  between the Settings and Main screens. All values are in base units (mA,
  mV, W, minutes) - no chemistry-scaled units anywhere in this dataclass.
- `presets.py` - battery chemistry presets that autofill `TestConfig`'s
  voltage-related fields only; current/power setpoints are pack-capacity-
  dependent and stay at generic defaults regardless of preset.

**`ui/`** - Tkinter screens, all children of a single `App(tk.Tk)`
(`ui/app.py`) that stacks every screen in the same container via
`.place(relwidth=1, relheight=1)` and raises one with `.lift()` - there's no
navigation/routing framework, just direct `app.show_x()` calls between
screens. Screens: `ConnectScreen`, `MainScreen` (both in `app.py`),
`SettingsScreen`, `RawScreen`, `WarningScreen`. `MainScreen` polls the
device's queues on a `self.after(...)` timer (`POLL_MS`/`REDRAW_MS`), not a
thread - same single-threaded-Tk rule as the queues above.

`ui/widgets.py` centralizes the shared look: touch-sized targets (~44px),
no hover/tooltip/right-click affordances, and the entire color palette -
**light theme only, by design** (Tk on macOS doesn't repaint text color for
dark mode, so `App.__init__` force-sets Aqua appearance rather than chasing
per-widget colors). Add new widgets here rather than hardcoding
colors/fonts in a screen file.

`ui/prefs.py` is the one JSON prefs file (`~/.battery_tester_ui/prefs.json`)
for small settings that survive restarts (warning acknowledgement, graph
view mode) - add new persisted keys to this shared dict rather than
creating another prefs file.

`ui/build_info.py` holds `VERSION`/`BUILD_DATE` for the About dialog;
`deploy/write_build_info.py` overwrites it at package/release time.

**Packaging** (`flatpak/`, `.github/workflows/release.yml`) - four independent
artifact types (source tarball, Flatpak, Windows exe, macOS app) built by
four different mechanisms for the same `main.py` entry point. The Flatpak
targets `org.freedesktop.Platform`, which has no Tkinter of its own: Tcl/Tk
9.0 are built from source, and tkinter itself is added via
[iwalton3/tkinter-standalone](https://github.com/iwalton3/tkinter-standalone)
(CPython's own `Lib/tkinter` + `_tkinter.c` built as a standalone extension
against those, pinned to the commit targeting this runtime's Python version)
rather than recompiling the SDK's Python. See the inline comments in
`flatpak/io.github.deeja.BatteryTesterKiosk.yml` before bumping
`runtime-version` - that pin and the tkinter-standalone commit must move
together, matching whatever Python version the new runtime ships.
