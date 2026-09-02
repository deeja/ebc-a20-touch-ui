# EBC-A20 Battery Tester UI

A native touchscreen app for the ZKETECH EBC-A20 battery capacity tester,
built for a Raspberry Pi Zero + JRP7006 touchscreen. Python + Tkinter (no
GPU/OpenGL toolkit, so it runs on an original armv6 Pi Zero without
compiling anything from source).

## What it does

- Connect screen: lists serial ports, connect/disconnect, or run against a
  built-in simulator with no hardware attached.
- Main screen: a live dual-line graph (voltage + current vs. time),
  numeric readouts (voltage, current, capacity, status), and touch controls
  to set a discharge current / cutoff voltage and start/stop a
  constant-current discharge test.

Out of scope by design (kept intentionally minimal): CSV export, saved test
profiles, battery-chemistry presets, charge-mode UI. The protocol driver
supports more than the UI exposes (see `ebc/protocol.py`) if you want to
extend it.

## ⚠️ Protocol verification needed

The EBC-A20 has no official protocol documentation. This app's serial
driver (`ebc/protocol.py`, `ebc/device.py`) is built from two independent
public reverse-engineering write-ups:

- https://gist.github.com/enkiusz/6408645efd622b8a638a14957cd37f47
- https://github.com/Kazhuu/ebc-battery-tester (`FRAMES.md`)

They **agree** on frame markers (`0xFA`/`0xF8`), the XOR checksum, and the
base-240 value encoding — and a worked example frame in the second source
checks out against the encoding math, which is good corroboration.

They **disagree** on serial parity: one says odd, the other says even
(8E1, over a CH340 USB adapter). This driver defaults to **even parity**
(`ebc/protocol.py` → `PARITY`). It has not been tested against a real
EBC-A20. If you connect real hardware and get no valid frames / constant
checksum failures, the first thing to try is flipping `PARITY` to
`serial.PARITY_ODD`.

Everything in this codebase has been exercised against the simulator, not
real hardware — treat the serial path as unverified until you've confirmed
it against your unit.

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
main.py              entry point
ebc/protocol.py       frame encode/decode, checksum, base-240 values
ebc/device.py         real EbcDevice (serial thread -> Queue of Sample)
ebc/mock_device.py     MockEbcDevice, same interface, synthetic data
ui/app.py             connect screen + main screen
ui/graph.py            dual-line strip chart (Tkinter Canvas)
ui/widgets.py           touch-sized buttons / steppers / readout tiles
deploy/                 systemd service + install script
```
