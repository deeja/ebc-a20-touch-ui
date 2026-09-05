#!/bin/sh
# Builds the downloadable source package: a .tar.gz containing just the
# app (main.py, requirements.txt, README.md, ebc/, ui/, assets/) - for anyone who'd
# rather `pip install -r requirements.txt` and run from source than use a
# packaged build (see flatpak/io.github.deeja.BatteryTesterKiosk.yml for the
# Flatpak, and the PyInstaller jobs in .github/workflows/release.yml for the
# Windows/macOS builds).
#
#   bash deploy/build-package.sh [version]
#
# version defaults to `git describe --tags --always` if not given (GitHub
# Actions passes the tag name explicitly). Output: dist/battery-tester-kiosk-<version>.tar.gz
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")

VERSION="${1:-$(cd "$REPO_DIR" && git describe --tags --always)}"
PKG_NAME="battery-tester-kiosk-$VERSION"

DIST_DIR="$REPO_DIR/dist"
STAGE_DIR="$DIST_DIR/$PKG_NAME"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

# Stamps ui/build_info.py in the checkout (read by the About dialog) - a
# side effect on your own working copy if run locally, harmless, just
# `git checkout -- ui/build_info.py` after if you don't want it dirtied.
python3 "$SCRIPT_DIR/write_build_info.py" "$VERSION"

cp "$REPO_DIR/main.py" "$REPO_DIR/requirements.txt" "$REPO_DIR/README.md" "$STAGE_DIR/"
cp -r "$REPO_DIR/ebc" "$REPO_DIR/ui" "$REPO_DIR/assets" "$STAGE_DIR/"
find "$STAGE_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +

(cd "$DIST_DIR" && tar czf "$PKG_NAME.tar.gz" "$PKG_NAME")
rm -rf "$STAGE_DIR"

echo "Built dist/$PKG_NAME.tar.gz"
