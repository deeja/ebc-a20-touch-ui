# Raspberry Pi Kiosk Image for Battery Tester UI

## Context

The battery tester UI (`ui/app.py`, Tkinter + `pyserial`) already has a kiosk-mode
code path (`EBC_KIOSK` env var → fullscreen + hidden cursor) and a `deploy/`
folder with a first-pass systemd service and install script, but that setup was
never actually wired to activate kiosk mode, and it assumes a full desktop
session (`DISPLAY=:0`, `graphical.target`) that doesn't exist on the headless
Raspberry Pi OS Lite install the README recommends. The goal now is to turn
this into a real, no-internet-needed, no-maintenance touchscreen kiosk on a
**Raspberry Pi Zero 2 W**, and to produce a **reusable flashable `.img`** so
new SD cards can be made without repeating manual setup each time.

Decisions already made:
- Target: Pi Zero 2 W, Raspberry Pi OS **Lite (32-bit/armhf)** — no desktop
  environment. Chosen over 64-bit after 64-bit's `qemu-aarch64` emulation
  proved unstable when actually building (segfaulted mid-debootstrap,
  nondeterministically, on WSL2); 32-bit's `qemu-arm` emulation is far more
  mature, and the app (pure Python/Tkinter) gets nothing from 64-bit.
- Deliverable: a golden `.img` file.
- **Not** doing read-only-root/overlayfs hardening — this isn't an unattended
  device; the user can power-cycle and access it, so standard writable
  filesystem is fine.
- Runtime needs zero network; building the image may use internet (apt/git).

Two build paths exist, both kept in the repo:
- **`deploy/pi-gen/`** (recommended) — builds the golden `.img` from scratch
  with [pi-gen](https://github.com/RPi-Distro/pi-gen), the same tool used to
  build Raspberry Pi OS itself. No physical Pi is needed until the final
  verification boot, since the image is assembled in a Docker/QEMU chroot on
  a dev machine (WSL2 on Windows), not cloned from a live SD card. This also
  sidesteps the golden-image cloning problems a captured card has (SSH host
  key duplication, the first-boot resize mechanism being single-use) since a
  freshly built image behaves exactly like an official Raspberry Pi OS
  release on every boot.
- **`deploy/install.sh`** — provisions an already-running Pi in place. Still
  the right tool for updating one already-deployed physical unit without a
  full rebuild+reflash, or for anyone who'd rather provision by hand.

Both paths install the same configuration, sourced from the same two files
(`deploy/xinitrc.template`, `deploy/profile-kiosk-block`) so they can't drift
apart.

## Repo changes

**`deploy/install.sh`** — rewrite (idempotent, safe to re-run):
- apt-get install adds `xserver-xorg xinit x11-xserver-utils`; drops `python3-pip`
  (Bookworm's Python is externally-managed — pip install will refuse; apt's
  `python3-serial` already covers the one dependency). Keep `pip install -r
  requirements.txt` documented as the dev-machine-only path.
- `usermod -aG dialout,video,tty,input "$USER"` (don't assume default groups).
- Write `/etc/systemd/system/getty@tty1.service.d/autologin.conf` directly
  (scripted drop-in, not a `raspi-config` shell-out).
- Append a marker-delimited block to `~/.profile` (not `.bash_profile` — that
  would shadow the stock file's PATH setup) that only launches X on tty1 local
  logins, not SSH sessions:
  ```
  if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    while true; do
      startx -- -nocursor
      sleep 2
    done
  fi
  ```
- Install `~/.xinitrc` (path substituted at install time, not hardcoded
  `/home/pi`): `xset s off`, `xset -dpms`, `xset s noblank`, `export
  EBC_KIOSK=1`, then launch via `systemd-cat -t ebc-kiosk python3
  "$INSTALL_DIR/main.py"` so a startup crash is visible in `journalctl -t
  ebc-kiosk` over SSH instead of just a black screen.
- Mask `NetworkManager-wait-online.service` if present (guard the check —
  don't error if absent) so shutdown/reboot isn't held up waiting on a network
  link that will never come.
- Set `allowed_users=console` in `/etc/X11/Xwrapper.config` if present, so a
  console-autologin `startx` is actually permitted to start X. If this is
  wrong, the failure mode is a silent black screen with no log anywhere
  `journalctl -t ebc-kiosk` reaches — worth setting explicitly rather than
  trusting the stock default.
- Refuses to run itself as root/sudo (checks `id -u`), since it needs to
  write `~/.profile`/`~/.xinitrc` as the target user and shells out to
  `sudo` itself for the privileged steps — running the whole script under
  `sudo` would otherwise leave those dotfiles root-owned.
- Drop `/etc/systemd/journald.conf.d/kiosk.conf` with a `SystemMaxUse=50M` cap
  — cheap, keeps logs from slowly filling the SD card, in scope for "no
  maintenance" without touching filesystem read-only-ness.
- Clean up any prior install: disable/remove the old `ebc-tester.service`.
- `systemctl daemon-reload`; final message telling the user to reboot.

**`deploy/ebc-tester.service`** — deleted (superseded by the autologin/xinit
mechanism; keeping it would imply a supported path that no longer exists).

**`deploy/xinitrc.template`** and **`deploy/profile-kiosk-block`** — the
two content blocks above, installed into place by `install.sh`.

**`ui/app.py`** — when `EBC_KIOSK` is set, Escape/F11 no longer un-fullscreen
the window. With no window manager present, an un-fullscreened Tk window has
no titlebar/way to move or close it — dead end without SSH. The binds stay
active for normal dev/windowed use.

**`README.md`** — update the "Raspberry Pi setup" section: reflect the new
apt package list, remove the now-stale "disable screen blanking yourself via
raspi-config" paragraph (handled automatically by `.xinitrc` now), and point
to `deploy/pi-gen/README.md` for building a flashable golden image. Update
the `deploy/` line in "Project layout" to match the new file set.

**`deploy/pi-gen/`** (new) — a pi-gen custom stage (`stage-kiosk`) plus a
`build.sh` wrapper that clones pi-gen's `master` (32-bit) branch, bundles this repo
into the image, and applies the same kiosk configuration as `install.sh`
(reusing `deploy/xinitrc.template` / `deploy/profile-kiosk-block` rather than
duplicating them) via `00-run.sh`/`00-run-chroot.sh` build-time scripts
instead of live `systemctl` calls, since there's no running systemd in a
build chroot. `config.example` is copied to a gitignored `config` locally
(it needs a real password). See `deploy/pi-gen/README.md` for full detail.

## Building and deploying (see `deploy/pi-gen/README.md` for full detail)

Building the image requires a Linux/Docker environment (WSL2 on Windows) and
is a long, bandwidth-heavy operation — only the last step below requires
physical hardware:

1. **One-time setup**: `cp deploy/pi-gen/config.example deploy/pi-gen/config`,
   fill in a real `FIRST_USER_PASS`.
2. **Build**: `sh deploy/pi-gen/build.sh` — clones pi-gen's `master` (32-bit)
   branch, bundles this repo
   into the image, applies the `stage-kiosk` customizations, runs the Docker
   build. Produces `battery-tester-kiosk-kiosk.img`.
3. **Flash** the `.img` to an SD card (Raspberry Pi Imager or Win32DiskImager).
4. **Verify on real hardware, with the touchscreen physically attached**:
   confirm fullscreen render at correct orientation, and **separately** that
   touch actually registers (tap a button — a dead-touch failure has a
   different cause than a display failure). If it doesn't come up, check
   `journalctl -t ebc-kiosk` over SSH first; if that's empty, X itself never
   started — check `~/.local/share/xorg/Xorg.0.log` (most likely
   `Xwrapper.config`). Optionally connect the EBC-A20 over USB-serial and
   smoke-test a real connection.
5. **Done** — because this image was built fresh rather than cloned from a
   live card, it already resizes to fill whatever card it's flashed to and
   gets fresh SSH host keys on every first boot, the same as any official
   Raspberry Pi OS release. No scrub/capture/shrink step is needed: the
   `.img` produced in step 2 is directly the deliverable, safe to flash to
   as many cards as needed.

## Explicitly out of scope

Read-only rootfs/overlayfs, SD-corruption hardening beyond the journald cap,
hardware watchdog/auto-reboot-on-hang, swap/zram tuning, `unclutter` (already
covered by `cursor="none"` + `startx -- -nocursor`) — all declined or
unnecessary given this isn't an unattended kiosk.

## Verification

- After step 4 above: app boots straight to fullscreen kiosk with no manual
  login, cursor hidden, touch responsive, "Use Simulator" produces a live
  graph, and a real EBC-A20 connects and streams data if available.
- `journalctl -t ebc-kiosk` shows clean output with no traceback.
- Confirm `deploy/install.sh` is idempotent by running it twice with no
  errors or duplicated `.profile` blocks (still relevant for the live-Pi
  provisioning path).
- Flashing the same `.img` to a second, different-sized card and booting it
  fills the new card and gets distinct SSH host keys, same as any stock
  Raspberry Pi OS image — confirming there's nothing golden-image-specific
  to go wrong.
