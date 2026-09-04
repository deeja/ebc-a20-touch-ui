#!/bin/sh
# Runs the app in a lightweight container (deploy/test/ui/) with its window
# forwarded to this machine's X server, so you can actually click around the
# UI without installing python3-tk/pyserial locally. Linux desktop only,
# with an X server (or XWayland) already running - $DISPLAY must be set.
#
# If a real EBC-A20 is plugged in over USB-serial, you'll be prompted to
# pass its device through to the container so the app can connect to actual
# hardware instead of just the simulator.
#
#   bash deploy/test-local-ui.sh                        # normal windowed mode
#   bash deploy/test-local-ui.sh --kiosk                 # EBC_KIOSK=1, fullscreen/no-cursor kiosk preview
#   bash deploy/test-local-ui.sh --device=/dev/ttyUSB0   # skip the prompt
set -e

if [ -z "$DISPLAY" ]; then
    echo "DISPLAY is not set - this needs a running X server (or XWayland)." >&2
    exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")
IMAGE=battery-tester-ui-test
CONTAINER=battery-tester-ui-test

ENV_ARGS=""
SELECTED_DEVICE=""
for arg in "$@"; do
    case "$arg" in
        --kiosk) ENV_ARGS="-e EBC_KIOSK=1" ;;
        --device=*) SELECTED_DEVICE="${arg#--device=}" ;;
    esac
done

# --- Offer to pass a USB-serial device (the EBC-A20) through to the container
if [ -z "$SELECTED_DEVICE" ]; then
    DEVICES=""
    for f in /dev/ttyUSB* /dev/ttyACM*; do
        [ -e "$f" ] && DEVICES="$DEVICES $f"
    done

    if [ -n "$DEVICES" ] && [ -t 0 ]; then
        echo "USB serial device(s) found:"
        i=1
        for d in $DEVICES; do
            echo "  $i) $d"
            i=$((i + 1))
        done
        echo "  0) none - use the simulator only"
        printf "Pass through which device? [0]: "
        read -r CHOICE
        CHOICE=${CHOICE:-0}
        if [ "$CHOICE" != "0" ]; then
            i=1
            for d in $DEVICES; do
                [ "$i" = "$CHOICE" ] && SELECTED_DEVICE="$d"
                i=$((i + 1))
            done
        fi
    elif [ -n "$DEVICES" ]; then
        echo "USB serial device(s) found ($DEVICES) but no interactive terminal to" >&2
        echo "prompt - continuing without passthrough. Rerun with --device=<path> to use one." >&2
    fi
fi

DEVICE_ARGS=""
if [ -n "$SELECTED_DEVICE" ]; then
    echo "==> Passing through $SELECTED_DEVICE"
    DEVICE_ARGS="--device=$SELECTED_DEVICE"
fi

echo "==> Building UI test image"
docker build -q -t "$IMAGE" "$SCRIPT_DIR/test/ui" >/dev/null

# Let local (non-network) clients connect to the X server - undone on exit.
# Docker containers don't share your ~/.Xauthority cookie by default, so
# without this the app fails to open the display.
XHOST_WAS_SET=0
if command -v xhost >/dev/null 2>&1; then
    xhost +local:docker >/dev/null 2>&1 && XHOST_WAS_SET=1
fi
cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    [ "$XHOST_WAS_SET" = 1 ] && xhost -local:docker >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Launching UI - close its window, or Ctrl+C here, to stop"
docker run --rm --name "$CONTAINER" \
    -e DISPLAY="$DISPLAY" $ENV_ARGS \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$REPO_DIR:/app:ro" \
    $DEVICE_ARGS \
    "$IMAGE" python3 main.py
