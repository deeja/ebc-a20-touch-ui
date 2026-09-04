#!/bin/sh
# Stands in for systemctl in the test container (deploy/test/Dockerfile),
# which has no init system running to actually talk to. Logs the call and
# succeeds, except `list-unit-files`, which prints nothing so install.sh's
# "is this unit present" checks correctly treat every unit as absent.
echo "[systemctl-stub] $*" >&2
case "$1" in
    list-unit-files) ;;
esac
exit 0
