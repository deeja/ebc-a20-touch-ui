#!/bin/sh
# Builds the downloadable deployment package: a .tar.gz containing the app
# plus deploy/install.sh and its kiosk templates, ready to extract on a Pi
# and run `sh deploy/install.sh` from inside it.
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
mkdir -p "$STAGE_DIR/deploy"

cp "$REPO_DIR/main.py" "$REPO_DIR/requirements.txt" "$REPO_DIR/README.md" "$STAGE_DIR/"
cp -r "$REPO_DIR/ebc" "$REPO_DIR/ui" "$STAGE_DIR/"
find "$STAGE_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +

cp "$REPO_DIR/deploy/install.sh" "$REPO_DIR/deploy/xinitrc.template" \
   "$REPO_DIR/deploy/profile-kiosk-block" "$STAGE_DIR/deploy/"

(cd "$DIST_DIR" && tar czf "$PKG_NAME.tar.gz" "$PKG_NAME")
rm -rf "$STAGE_DIR"

echo "Built dist/$PKG_NAME.tar.gz"
