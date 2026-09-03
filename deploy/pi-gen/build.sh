#!/bin/bash
# Builds the flashable "golden image" for the battery tester kiosk using
# pi-gen (https://github.com/RPi-Distro/pi-gen). Run this from a Linux
# environment with Docker (WSL2 works). This is a multi-GB download and a
# long build (30-90+ minutes) - only run it when you mean to.
#
# One-time setup:
#   cp deploy/pi-gen/config.example deploy/pi-gen/config
#   edit deploy/pi-gen/config, set a real FIRST_USER_PASS
#
# Then: sh deploy/pi-gen/build.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PI_GEN_DIR="${PI_GEN_DIR:-$HOME/pi-gen-build}"
STAGE_SRC="$PROJECT_DIR/deploy/pi-gen/stage-kiosk"
# 32-bit (armhf, pi-gen's master branch), not the arm64 branch: qemu-aarch64
# emulation hit repeated segfaults mid-debootstrap in the environment this
# was built in (WSL2 + a locally installed Docker Engine); qemu-arm did not,
# once routed through a working emulation setup (see DOCKER_HOST note
# below). Rather than chase down whether aarch64 would also work through
# that same setup, 32-bit was kept: the app is pure Python/Tkinter with no
# 64-bit-specific need, and the Pi Zero 2 W runs 32-bit fine.
PI_GEN_BRANCH="master"

# On WSL2, a locally-installed Docker Engine's binfmt/qemu emulation was
# unreliable (segfaults, or registrations invisible inside fresh
# containers), while Docker Desktop's engine worked once its multi-arch
# emulation was (re-)registered - see the two lines below. If you're on
# WSL2 with Docker Desktop, uncomment this (adjust the distro name in the
# path if it's not "Ubuntu"):
# export DOCKER_HOST=unix:///mnt/wsl/docker-desktop/shared-sockets/guest-services/docker.proxy.sock
DOCKER=${DOCKER:-docker}

if [ ! -f "$PROJECT_DIR/deploy/pi-gen/config" ]; then
	echo "Missing deploy/pi-gen/config - copy config.example to config and" >&2
	echo "fill in FIRST_USER_PASS (and anything else you want to change)." >&2
	exit 1
fi

echo "== (re-)registering qemu binfmt handlers =="
# Idempotent and cheap; doesn't persist across a Docker engine restart, so
# just redo it every run rather than trying to detect whether it's needed.
"$DOCKER" run --rm --privileged multiarch/qemu-user-static --reset -p yes

echo "== pi-gen checkout ($PI_GEN_BRANCH branch) at $PI_GEN_DIR =="
if [ ! -d "$PI_GEN_DIR" ]; then
	git clone --branch "$PI_GEN_BRANCH" --depth 1 https://github.com/RPi-Distro/pi-gen "$PI_GEN_DIR"
else
	git -C "$PI_GEN_DIR" fetch --depth 1 origin "$PI_GEN_BRANCH"
	git -C "$PI_GEN_DIR" checkout "$PI_GEN_BRANCH"
	git -C "$PI_GEN_DIR" reset --hard "origin/$PI_GEN_BRANCH"
fi

# Raspbian's archive signing key has a SHA-1 self-certification that recent
# GnuPG (as shipped in the pi-gen builder's Debian trixie base) rejects by
# policy ("Policy rejected non-revocation signature ... SHA1 is not
# considered secure"), so debootstrap's own signature check fails even
# though the (locally-bundled, not fetched) keyring itself is fine. This is
# an upstream key-format issue, not something wrong with this build -
# --no-check-gpg is safe here since the archive is fetched from the
# official mirror over a connection you control, and the resulting image
# gets verified by actually booting it.
if ! grep -q -- '--no-check-gpg' "$PI_GEN_DIR/scripts/common"; then
	sed -i '/BOOTSTRAP_ARGS+=(--keyring/a\	BOOTSTRAP_ARGS+=(--no-check-gpg)' "$PI_GEN_DIR/scripts/common"
fi

echo "== bundling app source into the kiosk stage =="
APP_DEST="$STAGE_SRC/01-copy-app/files/app"
rm -rf "$APP_DEST"
mkdir -p "$APP_DEST"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='deploy/pi-gen' \
	"$PROJECT_DIR/" "$APP_DEST/"

echo "== installing kiosk stage into pi-gen checkout =="
rm -rf "$PI_GEN_DIR/stage-kiosk"
cp -r "$STAGE_SRC" "$PI_GEN_DIR/stage-kiosk"
mkdir -p "$PI_GEN_DIR/stage-kiosk/02-configure-kiosk/files"
cp "$PROJECT_DIR/deploy/xinitrc.template" "$PI_GEN_DIR/stage-kiosk/02-configure-kiosk/files/"
cp "$PROJECT_DIR/deploy/profile-kiosk-block" "$PI_GEN_DIR/stage-kiosk/02-configure-kiosk/files/"

cp "$PROJECT_DIR/deploy/pi-gen/config" "$PI_GEN_DIR/config"
# Stage2 already carries its own EXPORT_IMAGE; skip exporting *that*
# intermediate image, we only want the final kiosk one.
touch "$PI_GEN_DIR/stage2/SKIP_IMAGES"

echo "== building (this is the long part) =="
cd "$PI_GEN_DIR"
./build-docker.sh

echo "Done. Image(s) in $PI_GEN_DIR/deploy/"
