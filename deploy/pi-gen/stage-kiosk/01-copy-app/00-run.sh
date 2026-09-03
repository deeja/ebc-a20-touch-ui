#!/bin/bash -e
# files/app is populated by deploy/pi-gen/build.sh (rsync of the live repo)
# before this stage runs - not committed to git, see files/app/.gitkeep.
install -d "${ROOTFS_DIR}/opt/battery-tester"
cp -r files/app/. "${ROOTFS_DIR}/opt/battery-tester/"
