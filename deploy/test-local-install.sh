#!/bin/sh
# Builds the deployment package and installs it inside an ephemeral Docker
# container (deploy/test/), exercising deploy/install.sh end-to-end - real
# apt package installs, group/profile/xinitrc handling, unit-file writes -
# without touching this machine or needing a physical Pi. Requires Docker.
#
# The container has no init system running (unlike a real Pi), so systemctl
# is stubbed (deploy/test/systemctl-stub.sh): install.sh's file-writing
# logic gets fully tested, but actual systemd integration (autologin,
# console kiosk boot) can only be verified on real hardware - see
# docs/pi-kiosk-plan.md.
#
#   bash deploy/test-local-install.sh
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
IMAGE=battery-tester-install-test
CONTAINER=battery-tester-install-test
VERSION=test-local

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

echo "==> Building deployment package"
sh "$SCRIPT_DIR/build-package.sh" "$VERSION"
PKG="$REPO_DIR/dist/battery-tester-kiosk-$VERSION.tar.gz"

echo "==> Building test container image"
docker build -q -t "$IMAGE" "$SCRIPT_DIR/test" >/dev/null

echo "==> Starting container"
docker run -d --name "$CONTAINER" "$IMAGE" >/dev/null

echo "==> Copying package into container"
docker cp "$PKG" "$CONTAINER:/tmp/pkg.tar.gz"
docker exec "$CONTAINER" sh -c 'mkdir -p /home/tester/app && tar xzf /tmp/pkg.tar.gz --strip-components=1 -C /home/tester/app && chown -R tester:tester /home/tester/app'

echo "==> Running deploy/install.sh as an unprivileged user"
docker exec -u tester -e USER=tester -e HOME=/home/tester -w /home/tester/app "$CONTAINER" sh deploy/install.sh

echo "==> Re-running install.sh to check idempotency"
docker exec -u tester -e USER=tester -e HOME=/home/tester -w /home/tester/app "$CONTAINER" sh deploy/install.sh

echo "==> Verifying results"
docker exec -u tester "$CONTAINER" sh -c '
    set -e
    test -f "$HOME/.xinitrc"
    [ "$(grep -Fxc "# >>> ebc-kiosk >>>" "$HOME/.profile")" = "1" ]
'
docker exec "$CONTAINER" test -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
docker exec "$CONTAINER" test -f /etc/systemd/journald.conf.d/kiosk.conf

echo "==> Local install test passed"
