#!/bin/sh
# Uninstalls and reinstalls the locally-built Flatpak bundle
# (ebc-a20-touch-ui-x86_64.flatpak, produced by build-flatpak-local.sh)
# on this machine's host flatpak install - useful for picking up a rebuilt
# bundle without the extra "flatpak install" prompt-for-already-installed
# confirmation, or for clearing a broken user install.
#
#   bash deploy/reinstall-flatpak-local.sh          # reinstall, then run it
#   bash deploy/reinstall-flatpak-local.sh --build  # reinstall only, don't run
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
APP_ID=io.github.deeja.EbcA20TouchUi
ARCH=x86_64
BUNDLE="$REPO_DIR/ebc-a20-touch-ui-$ARCH.flatpak"

if ! command -v flatpak >/dev/null 2>&1; then
    echo "flatpak not found on this machine - install it first:" >&2
    echo "  sudo apt install flatpak" >&2
    exit 1
fi

if [ ! -f "$BUNDLE" ]; then
    echo "$BUNDLE not found - build it first with deploy/build-flatpak-local.sh" >&2
    exit 1
fi

echo "==> Uninstalling $APP_ID (if installed)"
flatpak uninstall --user -y "$APP_ID" || true

echo "==> Installing from $BUNDLE"
flatpak install --user -y --bundle "$BUNDLE"

if [ "$1" = "--build" ]; then
    exit 0
fi

echo "==> Running $APP_ID"
flatpak run "$APP_ID"
