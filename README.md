# EBC-A20 Battery Tester UI

A native touchscreen app for the ZKETECH EBC-A20 battery capacity tester,
built for a Raspberry Pi Zero + JRP7006 touchscreen. Python + Tkinter (no
GPU/OpenGL toolkit, so it runs on an original armv6 Pi Zero without
compiling anything from source).

> ## ⚠️ FOR EXPERTS ONLY - READ BEFORE USE
>
> This tool drives real charge/discharge hardware against real batteries.
> Charging and discharging batteries outside their safe parameters can cause
> fire, explosion, toxic gas release, or permanent damage to the battery,
> the EBC-A20, or its surroundings - lithium chemistries especially so.
>
> **If you do not already understand battery chemistry - safe voltage
> cutoffs, C-rates, charge termination behavior, and the specific risks of
> the chemistry you're testing - do not use this tool.** Nothing here
> teaches or verifies that knowledge for you: the settings screen lets you
> pick numbers, it doesn't know what's safe for the cell in front of you.
>
> This software is provided with **no warranty of any kind**, and its
> authors and contributors accept **no responsibility or liability** for
> any damage, injury, fire, or loss arising from its use, including from
> bugs, incorrect readings, or protocol misinterpretation (see the protocol
> verification status below). You use it, and the hardware it controls,
> entirely at your own risk.

## Huge thanks to


## A note on AI assistance and other libraries, etcetera...

`/ai-off` *Claude, don't you dare change this part, or I swear I'll come for you...*

There was a huge amount of AI assistance on this project. Particularly Claude Sonnet.

If you are a python person and you happen to look through the code, you will *very likely* scream at your monitor; and I completely understand.

When AI writes code in .Net (my usual language), it causes me pain.

I will say though that this program probably wouldn't have been made if it wasn't for AI.
Given this program is for a kiosk on a Raspberry Pi Zero 2, Python is the best language choice for me as I *somewhat* know it
 **but** not well enough that I can do what I need to do myself. 

.Net / C# might work, but I haven't had good times trying to make it work on the smaller Pis and I didn't want to do that today.

A massive shoutout to these projects that were obviously assimilated by the borg:

- **[enkiusz's EBC-A20 gist](https://gist.github.com/enkiusz/6408645efd622b8a638a14957cd37f47)**
- **[Kazhuu/ebc-battery-tester](https://github.com/Kazhuu/ebc-battery-tester)**

@Kazhuu @enkiusz - as we say in NZ, thanks heaps!

Anyway, I hope this is useful. Sorry about the mess. 

`/ai-on`

## What it does

- Connect screen: lists serial ports, connect/disconnect, or run against a
  built-in simulator with no hardware attached.
- Main screen: a live chart - Voltage and Current on the left axis,
  Capacity on the right, each independently auto-scaled - numeric readouts
  (voltage, current, capacity, status), and Configure / Raw / Start / Stop /
  Disconnect controls. See **Usage** below for what the chart itself and
  the Raw Values screen can do.
- Settings screen (`ui/settings_screen.py`): pick a battery chemistry
  preset (Li-ion, LiPo, LiFePO4, LTO, 6V/12V lead-acid, NiMH, NiCd) and
  cell count to autofill voltage/cutoff fields, pick a test mode, and set
  that mode's parameters. Modes match the device's own manual: DSC-CC
  (constant-current discharge), DSC-CP (constant-power discharge), CHG-CV
  (constant-voltage charge), and **Repeat** — a configurable N-cycle (or
  continuous) Charge→rest→Discharge→rest loop, orchestrated by this app
  rather than the device's firmware (see `ebc/sequencer.py` — there's no
  confirmed wire command for the device's native single-shot Auto test).
- NiMH/NiCd presets are discharge-only: the device's one charge mode
  terminates on a current-taper-at-fixed-voltage, which can't detect the
  -ΔV peak that NiMH/NiCd charging needs to stop safely. The manual only
  lists lithium and lead-acid for charging; the Settings screen shows a
  warning if you pick NiMH/NiCd with a charge-involving mode, but doesn't
  block it.

Out of scope by design (kept intentionally minimal): saved test profiles
beyond the single active config, mid-test parameter adjustment (the
CONTINUE commands exist in the protocol but aren't wired up).

## Usage

1. **Connect** - pick a serial port, or tap "Use Simulator (no hardware)"
   to try the whole UI without a device attached.
2. **Configure** - choose a battery preset (or Custom) and cell count, pick
   a test mode, and set that mode's parameters. Nothing can run until this
   has been saved at least once - the main screen shows "Not configured"
   until then.
3. **Start / Stop** - starts the configured test on the device; Stop ends
   it (or, in Repeat mode, ends the cycle currently in progress).
4. **The live chart** - Voltage and Current (left axis, each independently
   auto-scaled) and Capacity (right axis) plotted against elapsed time.
   - **Tap the chart** to open its view options: a scrolling time window
     (tap the duration to type a new one, in seconds or minutes) or "Fit
     All" to show the whole run; "Start Y at 0" to force the axes to a zero
     baseline; **Export** to save everything currently held as a CSV, named
     with the test mode/preset and the data's start/end time; **Clear
     Graph** to wipe it (asks for confirmation first). Tap anywhere outside
     the popup to dismiss it.
   - **Drag a finger or the mouse** across the chart for a crosshair and a
     readout of time/voltage/current/capacity at that point.
   - Chart data is kept for the whole session - switching to Configure or
     Raw Values and back doesn't lose it; only a fresh connection or
     "Clear Graph" does.
5. **Raw** (button next to Configure) - a live, virtual-scrolling log of
   every raw frame from the device: hex bytes alongside their decoded
   fields, with Export/Clear buttons and an Autoscroll checkbox. Only
   populated against real hardware - the simulator has no real serial
   frames to show, so this stays empty when using it.

## Screenshots

Taken running against real hardware - a 4S LiFePO4 pack on the EBC-A20.

| | |
|---|---|
| ![Configure screen - LiFePO4 12V/4S preset, Repeat mode](docs/screenshots/01-configure.png) | ![Main screen mid-charge in Repeat mode](docs/screenshots/02-main-screen-charging.png) |
| Configure - battery preset, mode, and parameters | Main screen - live chart, readouts, controls |
| ![Chart view popup open over the live chart](docs/screenshots/03-chart-view-popup.png) | ![Raw Values screen with hex and decoded frames](docs/screenshots/04-raw-values.png) |
| Chart view popup - scroll window, Fit All, zero baseline, Export, Clear | Raw Values - hex alongside decoded fields |
| ![Main screen mid-discharge in constant-power mode](docs/screenshots/05-main-screen-discharge-cp.png) | |
| Main screen - a later run, discharging at constant power | |

## ⚠️ Protocol verification status

The EBC-A20 has no official protocol documentation. This app's serial
driver (`ebc/protocol.py`, `ebc/device.py`) is built from two independent
public reverse-engineering write-ups:

- https://gist.github.com/enkiusz/6408645efd622b8a638a14957cd37f47
- https://github.com/Kazhuu/ebc-battery-tester (`FRAMES.md`)

They **agree** on frame markers (`0xFA`/`0xF8`), the XOR checksum, and the
base-240 value encoding — and a worked example frame in the second source
checks out against the encoding math, which is good corroboration.

They **disagreed** on serial parity: one says odd, the other says even
(8E1, over a CH340 USB adapter). This driver defaults to **even parity**
(`ebc/protocol.py` → `PARITY`), and **that's now confirmed correct** — the
app connects to a real EBC-A20 and receives valid, checksum-passing frames.

**Confirmed-and-fixed against real hardware:** the live status frame's
voltage field was decoded with an incorrect ×10 factor (a holdover from the
docs' SET-command scaling table, wrongly applied to this different,
live-readback field) — readings were 10x too high. Fixed in
`parse_status_frame()`; see the note there for the underlying mixup.

**Still unverified:** `current_ma` in that same status frame uses the same
×10-decode pattern the voltage field wrongly had — it hasn't been
independently checked against a multimeter/known load yet, so if displayed
current looks off by a clean factor, that's the first place to look. The
CP-discharge (`0x11`) and CV-charge (`0x21`) commands and their status codes
are also still unverified against real hardware.

One more data point: the `Kazhuu/ebc-battery-tester` worked example
(`fa 01 00 14 01 5a 00 00 4b f8`) states its own checksum as
`0x01^0x00^0x14^0x01^0x5a^0x00^0x00 = 0x4b`, but that XOR actually
evaluates to `0x4e` (confirmed both by hand and in code — see the
`build_command()` sanity check below). So the source has an internal typo
in that one example; the plain-XOR algorithm it describes in prose is what
this driver implements, and it's corroborated independently by the
enkiusz gist.

## Running it

On a dev machine (Windows/Mac/Linux), no hardware needed:

```
pip install -r requirements.txt
python main.py
```

Click "Use Simulator" on the connect screen to see the full UI with
synthetic discharge data.

## Raspberry Pi setup

Targets a headless Raspberry Pi OS Lite install (no desktop environment) —
the app runs as the only thing on the display, launched via a minimal X
session on the console.

1. Flash Raspberry Pi OS Lite, enable SSH, get the Pi on the network (needed
   for this one-time setup only — the running kiosk needs no network at all).
2. Wire up the JRP7006 touchscreen per its own instructions (HDMI + USB for
   touch; it's a 1024x600 panel, which is what the UI defaults its window
   size to — it also reads the real screen size at runtime, so this isn't
   load-bearing).
3. Get the app onto the Pi, e.g. `/home/pi/batterytesterui`. Either
   `git clone` this repo, or download and extract a packaged release from
   the [Releases page](https://github.com/deeja/batterytesterui/releases)
   (a `battery-tester-kiosk-<version>.tar.gz` containing just the app and
   `deploy/`, no dev-only files).
4. From inside that directory: `sh deploy/install.sh` — installs
   `python3-tk`/`python3-serial`/`xserver-xorg`/`xinit` from apt (no
   compiling), adds your user to the groups needed to open the serial port
   and drive the display/touch devices, enables console autologin on tty1,
   and wires `~/.profile` + `~/.xinitrc` to launch the UI full-screen with
   the cursor hidden and screen blanking disabled as soon as that console
   logs in. Safe to re-run.
5. Reboot. The app should come up full-screen on the touchscreen with no
   login prompt.

This is also the path for updating an already-deployed unit in place
(`git pull`, or download the newer release package, then re-run
`install.sh`) — there's no separate image to rebuild and reflash.

### Troubleshooting

To run it manually instead of at boot: `python3 main.py` (from an SSH
session, or a manual `startx` on the console).

If the kiosk fails to come up, SSH in and check `journalctl -t ebc-kiosk`
for a traceback. If that's empty, the app never got launched at all - check
`~/.local/share/xorg/Xorg.0.log` for an X-server startup failure instead
(most commonly `/etc/X11/Xwrapper.config` not allowing console-started X
sessions, which `install.sh` sets automatically, but re-check it if you've
customized that file).

For the full design rationale behind the kiosk setup, see
[`docs/pi-kiosk-plan.md`](docs/pi-kiosk-plan.md).

## Project layout

```
main.py               entry point
ebc/protocol.py        frame encode/decode, checksum, base-240 values, status codes, RawFrame (raw+decoded pairing for the Raw Values screen)
ebc/device.py           real EbcDevice (serial thread -> Queue of Sample, plus a raw_queue of every frame incl. checksum failures)
ebc/mock_device.py       MockEbcDevice, same interface, simulates all 3 modes (raw_queue stays empty - no real frames to show)
ebc/presets.py            battery chemistry preset table
ebc/config.py              TestConfig - the currently active mode + all per-mode params
ebc/sequencer.py            AutoCycleController - repeat-mode state machine
ui/app.py                connect screen + main (live) screen
ui/settings_screen.py     battery/mode/param configuration screen
ui/raw_screen.py           Raw Values screen - virtual-scroll log of raw frames + decoded fields
ui/graph.py               live chart (Tkinter Canvas): auto-scaled axes, drag tooltip, tap-to-open view popup (scroll window / Fit All / zero baseline / Export / Clear)
ui/warning_screen.py       one-time safety disclaimer, remembered via ui/prefs.py
ui/prefs.py                 shared JSON prefs file (chart view settings, warning acknowledgement)
ui/widgets.py              touch-sized buttons / steppers / dropdowns / toggles
deploy/                     install script + kiosk-launch templates
deploy/build-package.sh      builds the downloadable release .tar.gz
deploy/test-local-install.sh  tests build-package.sh + install.sh in Docker
deploy/test-local-ui.sh       runs the app in Docker, forwarded to your X server
docs/pi-kiosk-plan.md       Pi kiosk deployment design rationale
```
