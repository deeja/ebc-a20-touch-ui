# Building the golden image with pi-gen

This builds a complete, flashable `.img` for the Raspberry Pi Zero 2 W kiosk
without ever touching a physical Pi during the build - only for the final
verification boot. It uses [pi-gen](https://github.com/RPi-Distro/pi-gen),
the same tool the Raspberry Pi Foundation uses to build Raspberry Pi OS
itself.

Requires a Linux environment with Docker (WSL2 on Windows works) - it is not
run from this repo's Windows dev environment directly.

## One-time setup

```
cp deploy/pi-gen/config.example deploy/pi-gen/config
```

Edit `deploy/pi-gen/config` and set a real `FIRST_USER_PASS` (this becomes
the login used for the console autologin, and for SSH if you need it - it's
gitignored, never commit a real password).

## Build

```
sh deploy/pi-gen/build.sh
```

This clones pi-gen's `master` branch (32-bit/armhf - chosen over the `arm64`
branch because `qemu-aarch64` emulation proved unstable in practice, see
`docs/pi-kiosk-plan.md`), bundles the current state of this repo into the
image's `/opt/battery-tester`, applies the `stage-kiosk`
customizations (packages, console autologin, `.xinitrc`, screen-blanking
disabled, `EBC_KIOSK=1`), and runs the Docker build. Expect a multi-GB
download and 30-90+ minutes.

Output lands in `$PI_GEN_DIR/deploy/` (default `~/pi-gen-build/deploy/`) as
`battery-tester-kiosk-kiosk.img` (plus a checksum/zip depending on pi-gen's
default compression).

## What `stage-kiosk` does

- `00-install-packages` - `python3-tk`, `python3-serial`, `xserver-xorg`,
  `xinit`, `x11-xserver-utils`.
- `01-copy-app` - copies the repo (bundled in by `build.sh`) to
  `/opt/battery-tester` on the image.
- `02-configure-kiosk` - console autologin on tty1, `~/.xinitrc` /
  `~/.profile` wired to launch the app fullscreen via `startx`, screen
  blanking disabled, `Xwrapper.config` permits console-started X,
  `NetworkManager-wait-online.service` masked, journal size capped, and the
  login user added to the groups needed for the serial port and the
  display/touch devices.

This intentionally reuses `deploy/xinitrc.template` and
`deploy/profile-kiosk-block` - the same files `deploy/install.sh` uses for
provisioning a live Pi by hand - so the two paths can't drift apart.

## After the build

Flash the `.img` (Raspberry Pi Imager or Win32DiskImager) to an SD card,
boot it on the real Pi with the JRP7006 touchscreen attached, and verify:
fullscreen render, touch responds, and (if available) the EBC-A20 connects
over USB-serial. Because this is a fresh build rather than a clone of a
live system, there's no SSH-host-key duplication or first-boot-resize
concern to work around - the image resizes to fill whatever card it's
flashed to, and gets fresh SSH host keys, the normal way any Raspberry Pi OS
image does. Once verified, that one `.img` file is the deliverable - flash
it to as many cards as you need.

## Updating the image later

There's no incremental update path - re-run `deploy/pi-gen/build.sh` after
changing the app code or `stage-kiosk`, and reflash. For a one-off change to
an *already-deployed* physical Pi, it's faster to `git pull` on the device
and re-run `deploy/install.sh` instead of rebuilding and reflashing.
