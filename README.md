# EBC-A20 Battery Tester UI

A native touchscreen app for the ZKETECH EBC-A20 battery capacity tester,
built for a Raspberry Pi Zero + JRP7006 touchscreen. Python + Tkinter (no
GPU/OpenGL toolkit, so it runs on an original armv6 Pi Zero without
compiling anything from source).

## What it does

- Connect screen: lists serial ports, connect/disconnect, or run against a
  built-in simulator with no hardware attached.
- Main screen: a live dual-line graph (voltage + current vs. time),
  numeric readouts (voltage, current, capacity, status), and Configure /
  Start / Stop controls.
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

Out of scope by design (kept intentionally minimal): CSV export, saved test
profiles beyond the single active config, mid-test parameter adjustment
(the CONTINUE commands exist in the protocol but aren't wired up).

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

1. Flash Raspberry Pi OS (Lite is fine), enable SSH, get the Pi on the network.
2. Wire up the JRP7006 touchscreen per its own instructions (HDMI + USB for
   touch; it's a 1024x600 panel, which is what the UI defaults its window
   size to — it also reads the real screen size at runtime, so this isn't
   load-bearing).
3. Copy this project to the Pi, e.g. `/home/pi/batterytesterui`.
4. From inside the project directory: `sh deploy/install.sh` — installs
   `python3-tk`/`python3-serial` from apt (no compiling), adds your user to
   the `dialout` group so it can open `/dev/ttyUSB0` without root, and
   installs a systemd service that autostarts the UI on the desktop
   session.
5. Reboot. The app should come up full-screen on the touchscreen.

To run it manually instead of via systemd: `python3 main.py`.

Screen blanking/DPMS on a kiosk display is a display-manager setting, not
something this app controls — disable it via `raspi-config` or your
desktop environment's power settings if the screen goes to sleep.

## Project layout

```
main.py               entry point
ebc/protocol.py        frame encode/decode, checksum, base-240 values, status codes
ebc/device.py           real EbcDevice (serial thread -> Queue of Sample)
ebc/mock_device.py       MockEbcDevice, same interface, simulates all 3 modes
ebc/presets.py            battery chemistry preset table
ebc/config.py              TestConfig - the currently active mode + all per-mode params
ebc/sequencer.py            AutoCycleController - repeat-mode state machine
ui/app.py                connect screen + main (live) screen
ui/settings_screen.py     battery/mode/param configuration screen
ui/graph.py               dual-line strip chart (Tkinter Canvas)
ui/widgets.py              touch-sized buttons / steppers / dropdowns / toggles
deploy/                     systemd service + install script
```
