#!/bin/sh
# Run on the Raspberry Pi, from inside the project directory, as your normal
# user (not with sudo - it prompts for sudo itself where needed):
#   sh deploy/install.sh
# Safe to re-run - every step here is idempotent.
set -e

if [ "$(id -u)" = "0" ]; then
    echo "Run this as your normal user, not as root/sudo - it will prompt" >&2
    echo "for sudo itself where needed." >&2
    exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
INSTALL_DIR=$(dirname "$SCRIPT_DIR")
TARGET_USER="$USER"
TARGET_HOME="$HOME"

sudo apt-get update
# python3-serial covers the app's one dependency (pyserial). No python3-pip:
# Raspberry Pi OS Bookworm's system Python is externally-managed (PEP 668)
# and refuses `pip install` outside a venv - apt is the install path here.
sudo apt-get install -y python3-tk python3-serial xserver-xorg xinit x11-xserver-utils

sudo usermod -a -G dialout,video,tty,input "$TARGET_USER"

# --- Console autologin on tty1 ---------------------------------------------
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $TARGET_USER --noclear %I \$TERM
EOF

# --- X must be allowed to start from a console login, not just a display
#     manager - the default is usually fine, but pin it so a stock image
#     can't leave startx silently refusing to launch.
if [ -f /etc/X11/Xwrapper.config ]; then
    sudo sed -i 's/^allowed_users=.*/allowed_users=console/' /etc/X11/Xwrapper.config
fi

# --- Launch X + the app from the tty1 login shell ---------------------------
PROFILE="$TARGET_HOME/.profile"
touch "$PROFILE"
# Strip any block from a previous run, then append the current one, so
# re-running this script never stacks duplicate blocks. The leading printf
# guards against the marker landing mid-line if .profile doesn't already
# end in a newline.
sed -i '/^# >>> ebc-kiosk >>>$/,/^# <<< ebc-kiosk <<<$/d' "$PROFILE"
printf '\n' >> "$PROFILE"
cat "$SCRIPT_DIR/profile-kiosk-block" >> "$PROFILE"

sed "s#@INSTALL_DIR@#$INSTALL_DIR#g" "$SCRIPT_DIR/xinitrc.template" > "$TARGET_HOME/.xinitrc"
chmod +x "$TARGET_HOME/.xinitrc"
chown "$TARGET_USER:$TARGET_USER" "$PROFILE" "$TARGET_HOME/.xinitrc"

# --- Boot/shutdown polish: don't wait on a network that will never come -----
if systemctl list-unit-files 2>/dev/null | grep -q '^NetworkManager-wait-online\.service'; then
    sudo systemctl mask NetworkManager-wait-online.service
fi

# --- Cap journal size so logs can't slowly fill the SD card ------------------
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/kiosk.conf > /dev/null <<EOF
[Journal]
SystemMaxUse=50M
EOF

# --- Remove the old desktop-session-based systemd unit, if present ----------
if [ -f /etc/systemd/system/ebc-tester.service ]; then
    sudo systemctl disable --now ebc-tester.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/ebc-tester.service
fi

sudo systemctl daemon-reload

echo "Installed. Reboot to boot straight into the fullscreen kiosk on tty1:"
echo "  sudo reboot"
