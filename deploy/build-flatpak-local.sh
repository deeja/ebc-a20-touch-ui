#!/bin/sh
# Reproduces the GitHub Actions flatpak build locally with Docker, using the
# exact same container image (with the flathub remote and the
# org.freedesktop.Platform/Sdk//25.08 runtime already installed, avoiding a
# slow first-run download) and flatpak-builder invocation that the
# flatpak/flatpak-github-actions/flatpak-builder@v6 step runs in
# .github/workflows/release.yml - so packaging failures can be iterated on
# without a CI round-trip. See that action's index.js for where these exact
# flags come from (in particular --disable-rofiles-fuse, needed since FUSE
# isn't reliably available in a container).
#
# Not reproduced here: the action wraps flatpak-builder in `xvfb-run
# --auto-servernum` (for screenshot-composing/GUI-test edge cases this
# manifest doesn't use) - confirmed hanging forever in this Docker setup
# (Xvfb itself starts, but xvfb-run's own readiness wait never returns, so
# flatpak-builder never even launches - zero output, indefinitely). Skipped
# for the local build; CI still goes through the real action unchanged.
#
#   bash deploy/build-flatpak-local.sh          # build, then run it
#   bash deploy/build-flatpak-local.sh --build  # build only, don't run
#
# Leaves flatpak/builddir, flatpak/.flatpak-builder, flatpak/repo, and
# *.flatpak in the repo root (gitignored) - rerun freely, or
# `rm -rf flatpak/builddir flatpak/.flatpak-builder flatpak/repo *.flatpak`
# to start clean.
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
IMAGE=ghcr.io/flathub-infra/flatpak-github-actions:freedesktop-25.08
APP_ID=io.github.deeja.EbcA20TouchUi
MANIFEST=flatpak/io.github.deeja.EbcA20TouchUi.yml
ARCH=x86_64
BRANCH=master
BUNDLE=battery-tester-kiosk-$ARCH.flatpak

echo "==> Building (in $IMAGE)"
docker run --rm --privileged \
  --volume "$REPO_DIR":/data --workdir /data \
  "$IMAGE" \
  flatpak-builder \
    --repo=flatpak/repo \
    --disable-rofiles-fuse \
    --install-deps-from=flathub \
    --force-clean \
    --default-branch="$BRANCH" \
    --arch="$ARCH" \
    --state-dir flatpak/.flatpak-builder \
    flatpak/builddir "$MANIFEST"

echo "==> Creating bundle"
docker run --rm --privileged \
  --volume "$REPO_DIR":/data --workdir /data \
  "$IMAGE" \
  flatpak build-bundle flatpak/repo "$BUNDLE" \
    --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
    --arch="$ARCH" "$APP_ID" "$BRANCH"

echo "==> Built $BUNDLE"

if [ "$1" = "--build" ]; then
    exit 0
fi

if ! command -v flatpak >/dev/null 2>&1; then
    echo "flatpak not found on this machine - install it to run the bundle:" >&2
    echo "  sudo apt install flatpak" >&2
    exit 1
fi

echo "==> Installing and running (uses your host's flatpak, not the container - needs a display)"
flatpak install --user -y --bundle "$REPO_DIR/$BUNDLE"
flatpak run "$APP_ID"
