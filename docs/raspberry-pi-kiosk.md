# Raspberry Pi: boot straight into the kiosk

This turns a Raspberry Pi running standard Raspberry Pi OS into a dedicated
kiosk that boots directly into the `io.github.deeja.EbcA20TouchUi` Flatpak,
fullscreen, with no desktop shell, icons, or panel ever appearing - matching
this project's intended deployment target (see the `--socket=x11` comment in
[`flatpak/io.github.deeja.EbcA20TouchUi.yml`](../flatpak/io.github.deeja.EbcA20TouchUi.yml)).

It works by switching the Pi to **Console Autologin** (bypassing the
desktop's display manager entirely), then having the autologin shell start a
minimal X11 session whose only job is to run the Flatpak in a restart loop.
No window manager is used - the app already goes fullscreen itself via the
`EBC_KIOSK` env var baked into the Flatpak's launcher.

Tested on a Raspberry Pi Zero 2 W running Raspberry Pi OS (Debian 13
"trixie") with the default `lightdm` + `labwc` desktop.

## Prerequisites

- Install the Raspberry Pi 64bit **with Desktop** if using the Rpi Zero 2 as this seems to be the only supported image now. 

- The Flatpak is already installed, per [the main install instructions](../README.md#linux-including-raspberry-pi):
  ```bash
  flatpak install --user ./ebc-a20-touch-ui-<arch>.flatpak
  ```
- Your user is in the `dialout` group (needed for the app to open
  `/dev/ttyUSB*`/`/dev/ttyACM*` when the EBC-A20 is plugged in):
  ```bash
  sudo usermod -aG dialout $USER
  ```
  Log out and back in for that to take effect.
- `Xorg`/`startx` are present - true by default on any Raspberry Pi OS image
  that ships the desktop, since it already relies on them.

## 1. Switch boot behaviour to console autologin

```bash
sudo raspi-config nonint do_boot_behaviour B2
```

This sets the systemd default target to `multi-user.target`, stops the
desktop's display manager (`lightdm`) from being pulled in at boot, and
configures `agetty` to autologin your user on tty1.

## 2. Auto-start X only on the real console login

Append to `~/.bash_profile` (create it if it doesn't exist):

```bash
# --- ebc-a20 kiosk autostart ---
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx -- -nocursor
fi
```

`-nocursor` hides the mouse pointer, appropriate for a touchscreen. Guarding
on tty1 and an unset `$DISPLAY` stops this from firing over SSH or on a
second console.

## 3. `.xinitrc` - no window manager, just the app in a restart loop

Create `~/.xinitrc` and make it executable (`chmod +x ~/.xinitrc`):

```bash
#!/bin/sh
xset -dpms
xset s off
xset s noblank

while true; do
    flatpak run io.github.deeja.EbcA20TouchUi
    sleep 2
done
```

- The `xset` calls disable screen blanking/power-saving, standard for an
  always-on touchscreen kiosk.
- The `while true` loop relaunches the app a couple seconds after it exits
  for any reason (crash, device disconnect, unhandled exception), so the
  kiosk display doesn't go blank unattended.

## 4. Reboot and verify

```bash
sudo reboot
```

After it comes back up, the touchscreen should show the app fullscreen with
no panel/desktop ever appearing. To confirm from another machine over SSH:

```bash
systemctl get-default        # -> multi-user.target
systemctl is-active lightdm  # -> inactive
pgrep -af EbcA20TouchUi       # -> the app's python3 process, running under Xorg on tty1
```

Killing the app process (or unplugging/replugging the EBC-A20) should show
the restart loop relaunching it rather than leaving a blank screen.

## Rollback

Nothing here is destructive - the desktop packages (`lightdm`, `labwc`,
`pcmanfm-pi`, `wf-panel-pi`) are never removed, just not started:

- `sudo raspi-config nonint do_boot_behaviour B4` restores Desktop Autologin
  (the standard Raspberry Pi desktop) as it was before.
- Removing the appended block from `~/.bash_profile` and deleting
  `~/.xinitrc` removes the kiosk auto-start behaviour independently of the
  boot-target change.
