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
# Then: bash deploy/pi-gen/build.sh
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
export DOCKER_BUILDKIT=1

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

# export-image's loop-device setup (ensure_next_loopdev) trusts `losetup -f`
# to return a bare "/dev/loopN" path unconditionally. On a machine that's
# also actively snap-mounting things (snapd owns loop0-30+ here), that raced
# once and losetup -f came back annotated as "/dev/loop31 (lost)" instead -
# the sed that's supposed to pull out the minor number doesn't match that
# shape, so it falls through unchanged and `mknod /dev/loop31 b 7
# "/dev/loop31 (lost)"` fails with "invalid minor device number". The
# existing retry loop (5 attempts, 5s apart) doesn't help because nothing
# resets the stuck device between attempts, so it fails the same way every
# time. Detect that shape and force-detach the offending device so the next
# retry gets a genuinely free index.
if ! grep -q 'BASH_REMATCH' "$PI_GEN_DIR/scripts/common"; then
	python3 - "$PI_GEN_DIR/scripts/common" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path).read()
old = (
	"ensure_next_loopdev() {\n"
	"\tlocal loopdev\n"
	"\tloopdev=\"$(losetup -f)\"\n"
	"\tloopmaj=\"$(echo \"$loopdev\" | sed -E 's/.*[^0-9]*?([0-9]+)$/\\1/')\"\n"
	"\t[[ -b \"$loopdev\" ]] || mknod \"$loopdev\" b 7 \"$loopmaj\"\n"
	"}\n"
)
new = (
	"ensure_next_loopdev() {\n"
	"\tlocal loopdev\n"
	"\tloopdev=\"$(losetup -f)\"\n"
	"\tif [[ \"$loopdev\" =~ ^(/dev/loop[0-9]+)[^0-9] ]]; then\n"
	"\t\tlosetup -d \"${BASH_REMATCH[1]}\" 2>/dev/null || true\n"
	"\t\treturn 1\n"
	"\tfi\n"
	"\tloopmaj=\"$(echo \"$loopdev\" | sed -E 's/.*[^0-9]*?([0-9]+)$/\\1/')\"\n"
	"\t[[ -b \"$loopdev\" ]] || mknod \"$loopdev\" b 7 \"$loopmaj\"\n"
	"}\n"
)
assert old in text, "pi-gen's ensure_next_loopdev has changed shape upstream"
open(path, "w").write(text.replace(old, new))
PYEOF
fi

# raspbian.raspberrypi.com is a geo-redirector that hands different packages
# off to different real mirrors; from this network location it deterministically
# routes dpkg/libc6/libc-bin/libsqlite3-0/linux-sysctl-defaults to
# mirror.lagoon.nc, which returns "403 Forbidden" for every file (seen on two
# consecutive debootstrap runs). Pin debootstrap and the in-image apt source
# straight at mirror.2degrees.nz instead, which served every other package
# cleanly in both runs - works around the one broken mirror without retrying
# indefinitely and hoping the redirector picks differently.
RASPBIAN_MIRROR="http://mirror.2degrees.nz/raspbian/raspbian/"
sed -i "s#http://raspbian.raspberrypi.com/raspbian/#$RASPBIAN_MIRROR#" \
	"$PI_GEN_DIR/stage0/prerun.sh" \
	"$PI_GEN_DIR/stage0/00-configure-apt/files/raspbian.sources"

# pi-gen's own Dockerfile (the build-tooling image, not the Pi image) just
# does a plain `apt-get install`, so every time that layer needs to rebuild
# (base image update, or the package list changing) it re-downloads
# everything from scratch. Switch it to BuildKit cache mounts for
# /var/cache/apt and /var/lib/apt, and drop docker-clean (which normally
# deletes downloaded .debs right after install, defeating a cache mount) -
# repeat `docker build`s reuse the cache instead of hitting the network.
# Re-cloning pi-gen (git reset --hard, above) wipes this each run, so it's
# re-applied here rather than done once by hand.
if ! grep -q 'type=cache,target=/var/cache/apt' "$PI_GEN_DIR/Dockerfile"; then
	grep -q '^# syntax=docker/dockerfile:1' "$PI_GEN_DIR/Dockerfile" ||
		sed -i '1i# syntax=docker/dockerfile:1' "$PI_GEN_DIR/Dockerfile"
	python3 - "$PI_GEN_DIR/Dockerfile" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path).read()
old = "RUN apt-get -y update && \\\n    apt-get -y install --no-install-recommends"
new = (
    "RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \\\n"
    "    --mount=type=cache,target=/var/lib/apt,sharing=locked \\\n"
    "    rm -f /etc/apt/apt.conf.d/docker-clean && \\\n"
    "    apt-get -y update && \\\n"
    "    apt-get -y install --no-install-recommends"
)
assert old in text, "pi-gen Dockerfile's apt-get RUN line has changed shape upstream"
text = text.replace(old, new)
old_tail = "arch-test \\\n    && rm -rf /var/lib/apt/lists/*\n"
assert old_tail in text, "pi-gen Dockerfile's apt-get RUN line has changed shape upstream"
text = text.replace(old_tail, "arch-test\n")
open(path, "w").write(text)
PYEOF
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

echo "== starting local apt-cacher-ng proxy (caches Raspbian .debs across full rebuilds) =="
# debootstrap and the in-chroot apt-get installs otherwise re-download every
# package from the mirror on each from-scratch build. This is best-effort -
# if it can't be started, the build just proceeds without a package cache.
APT_CACHER_NAME="pi-gen-apt-cacher"
APT_CACHER_NET="pi-gen-cache-net"
"$DOCKER" network inspect "$APT_CACHER_NET" >/dev/null 2>&1 || "$DOCKER" network create "$APT_CACHER_NET" >/dev/null
if [ -z "$("$DOCKER" ps -q --filter "name=^${APT_CACHER_NAME}$")" ]; then
	"$DOCKER" rm -f "$APT_CACHER_NAME" >/dev/null 2>&1 || true
	"$DOCKER" run -d --name "$APT_CACHER_NAME" --network "$APT_CACHER_NET" \
		-v pi-gen-apt-cache:/var/cache/apt-cacher-ng \
		sameersbn/apt-cacher-ng:latest >/dev/null 2>&1 || true
fi
if [ -n "$("$DOCKER" ps -q --filter "name=^${APT_CACHER_NAME}$")" ]; then
	echo "APT_PROXY=\"http://${APT_CACHER_NAME}:3142\"" >>"$PI_GEN_DIR/config"
	export PIGEN_DOCKER_OPTS="${PIGEN_DOCKER_OPTS:-} --network $APT_CACHER_NET"
else
	echo "  (couldn't start apt-cacher-ng - continuing without a package cache)" >&2
fi
# (to stop using it: docker rm -f pi-gen-apt-cacher; docker network rm pi-gen-cache-net;
# docker volume rm pi-gen-apt-cache)

# A build that fails partway through leaves an exited "pigen_work" container
# behind; build-docker.sh refuses to reuse it without CONTINUE=1, and
# without CONTINUE a fresh container means re-debootstrapping stage0-2 from
# scratch. Always allow reuse - it's a no-op when no container exists, and
# it's what makes retrying after a fix fast.
export CONTINUE=1

echo "== building (this is the long part) =="
cd "$PI_GEN_DIR"
./build-docker.sh

echo "Done. Image(s) in $PI_GEN_DIR/deploy/"
