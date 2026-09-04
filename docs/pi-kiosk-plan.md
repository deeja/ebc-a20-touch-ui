# Raspberry Pi Kiosk Deployment for Battery Tester UI

## Context

The battery tester UI (`ui/app.py`, Tkinter + `pyserial`) has a kiosk-mode
code path (`EBC_KIOSK` env var → fullscreen + hidden cursor). `deploy/`
holds `install.sh`, which provisions an already-flashed, headless Raspberry
Pi OS Lite install (no desktop environment) into a **Raspberry Pi Zero 2 W**
touchscreen kiosk: console autologin, a minimal X session launching the app
full-screen, screen blanking disabled, and no dependency on the network at
runtime.

Decisions already made:
- Target: Pi Zero 2 W, Raspberry Pi OS **Lite (32-bit/armhf)** — no desktop
  environment.
- **Not** doing read-only-root/overlayfs hardening — this isn't an
  unattended device; the user can power-cycle and access it, so a standard
  writable filesystem is fine.
- Runtime needs zero network; provisioning needs internet (apt) only.

### Golden-image build (tried, then dropped)

An earlier version of this plan built a complete, flashable `.img` from
scratch with [pi-gen](https://github.com/RPi-Distro/pi-gen) (`deploy/pi-gen/`,
now removed), so a new SD card could be made without repeating manual setup.
In practice this bought little over `install.sh` alone while costing a lot:
- A Docker + QEMU chroot build, multi-GB download, 30-90+ minutes per build.
- 64-bit (`arm64`) QEMU emulation proved outright unstable — segfaulted
  mid-debootstrap, nondeterministically, on WSL2 — forcing a fallback to the
  32-bit (`master`) pi-gen branch.
- `install.sh` alone provisions a stock, already-flashed card into the same
  kiosk in a couple of minutes, is idempotent (safe to re-run for updates),
  and needs no Docker/QEMU toolchain at all.

Given the app itself needs no special image customization beyond what
`install.sh` already does, the golden-image path wasn't worth its
build-tooling weight. It was removed in favor of distributing the app
itself as a downloadable package (see below) that `install.sh` runs
against.

## Deployment: downloadable package + install script

`deploy/build-package.sh` bundles the app (`main.py`, `ebc/`, `ui/`,
`requirements.txt`, `README.md`) together with `deploy/install.sh` and its
templates (`deploy/xinitrc.template`, `deploy/profile-kiosk-block`) into
`dist/battery-tester-kiosk-<version>.tar.gz` — no dev-only files
(`.git`, `.vscode`, `__pycache__`) included.

A GitHub Actions workflow (`.github/workflows/release.yml`) runs this
script and publishes the resulting tarball as a release asset whenever a
`v*` tag is pushed, so deploying a unit is: download the release package,
extract it on the Pi, run `sh deploy/install.sh`. `git clone` works too if
you want a dev checkout instead of a release build — both feed the same
`install.sh`.

### Testing without a Pi

`deploy/test-local-install.sh` builds the package and runs `install.sh`
against it inside an ephemeral Docker container (`deploy/test/`), on any
dev machine with Docker - no hardware, and nothing touches the host. The
container has no init system running, so `systemctl` is stubbed there
(`deploy/test/systemctl-stub.sh`); everything else - apt package installs,
group membership, `~/.profile`/`~/.xinitrc` writes, unit-file writes, and
idempotency (it runs `install.sh` twice) - is exercised for real. Actual
systemd integration (autologin firing, the unit mask taking effect) still
needs the real-hardware check below.

To actually see and click around the UI without a Pi, `deploy/test-local-ui.sh`
runs `main.py` in a much lighter container (`deploy/test/ui/` - just
`python3-tk`/`python3-serial`, no X server of its own) with its window
forwarded to the host's X server (`-v /tmp/.X11-unix`, `-e DISPLAY`,
temporary `xhost +local:docker`). Linux desktop with a running X server (or
XWayland) only. `--kiosk` sets `EBC_KIOSK=1` to preview the fullscreen/no-exit
kiosk behavior. If a real EBC-A20's USB-serial adapter is plugged in
(`/dev/ttyUSB*`/`/dev/ttyACM*`), it prompts to pass one through
(`--device=<path>` to skip the prompt) so the app can talk to real hardware
instead of just the simulator.

### `install.sh` (idempotent, safe to re-run)

- apt-get installs `python3-tk python3-serial xserver-xorg xinit
  x11-xserver-utils`. No `python3-pip`: Bookworm's system Python is
  externally-managed and refuses `pip install` outside a venv; apt's
  `python3-serial` already covers the one runtime dependency (`pip install
  -r requirements.txt` stays documented as the dev-machine-only path).
- `usermod -aG dialout,video,tty,input "$USER"`.
- Writes `/etc/systemd/system/getty@tty1.service.d/autologin.conf` directly
  (scripted drop-in, not a `raspi-config` shell-out).
- Appends a marker-delimited block to `~/.profile` (not `.bash_profile` —
  that would shadow the stock file's PATH setup) that only launches X on
  tty1 local logins, never over SSH:
  ```
  if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    while true; do
      startx -- -nocursor
      sleep 2
    done
  fi
  ```
- Installs `~/.xinitrc` (path substituted at install time, not hardcoded
  `/home/pi`): `xset s off`, `xset -dpms`, `xset s noblank`, `export
  EBC_KIOSK=1`, then launches via `systemd-cat -t ebc-kiosk python3
  "$INSTALL_DIR/main.py"` so a startup crash is visible in `journalctl -t
  ebc-kiosk` over SSH instead of just a black screen.
- Masks `NetworkManager-wait-online.service` if present (guarded — no error
  if absent) so shutdown/reboot isn't held up waiting on a network link
  that will never come.
- Sets `allowed_users=console` in `/etc/X11/Xwrapper.config` if present, so
  a console-autologin `startx` is actually permitted to start X. If wrong,
  the failure mode is a silent black screen with no log anywhere
  `journalctl -t ebc-kiosk` reaches.
- Refuses to run as root/sudo (checks `id -u`), since it needs to write
  `~/.profile`/`~/.xinitrc` as the target user and shells out to `sudo`
  itself for the privileged steps.
- Drops `/etc/systemd/journald.conf.d/kiosk.conf` with `SystemMaxUse=50M` —
  keeps logs from slowly filling the SD card.
- Cleans up any prior install: disables/removes the old
  `ebc-tester.service` desktop-session unit, if present.

**`ui/app.py`** — when `EBC_KIOSK` is set, Escape/F11 no longer
un-fullscreen the window. With no window manager present, an
un-fullscreened Tk window has no titlebar/way to move or close it — dead
end without SSH. The binds stay active for normal dev/windowed use.

## Explicitly out of scope

Read-only rootfs/overlayfs, SD-corruption hardening beyond the journald
cap, hardware watchdog/auto-reboot-on-hang, swap/zram tuning, `unclutter`
(already covered by `cursor="none"` + `startx -- -nocursor`) — all declined
or unnecessary given this isn't an unattended kiosk.

## Verification

- App boots straight to fullscreen kiosk with no manual login, cursor
  hidden, touch responsive, "Use Simulator" produces a live graph, and a
  real EBC-A20 connects and streams data if available.
- `journalctl -t ebc-kiosk` shows clean output with no traceback.
- `deploy/install.sh` is idempotent: running it twice produces no errors or
  duplicated `.profile` blocks.
- `deploy/build-package.sh` produces a tarball containing the app plus
  `deploy/install.sh` and its templates, and nothing dev-only
  (`.git`/`.vscode`/`__pycache__`).
- `bash deploy/test-local-install.sh` passes: package builds, `install.sh`
  runs clean twice in the container, and the expected files land in place.
