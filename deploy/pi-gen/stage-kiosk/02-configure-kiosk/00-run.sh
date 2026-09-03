#!/bin/bash -e
# files/xinitrc.template and files/profile-kiosk-block are copied in by
# deploy/pi-gen/build.sh from the canonical deploy/ versions (not duplicated
# here) before this stage runs.

sed "s#@INSTALL_DIR@#/opt/battery-tester#g" files/xinitrc.template \
	> "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.xinitrc"
chmod +x "${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.xinitrc"

PROFILE="${ROOTFS_DIR}/home/${FIRST_USER_NAME}/.profile"
touch "${PROFILE}"
printf '\n' >> "${PROFILE}"
cat files/profile-kiosk-block >> "${PROFILE}"

install -d "${ROOTFS_DIR}/etc/systemd/system/getty@tty1.service.d"
cat > "${ROOTFS_DIR}/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${FIRST_USER_NAME} --noclear %I \$TERM
EOF

if [ -f "${ROOTFS_DIR}/etc/X11/Xwrapper.config" ]; then
	sed -i 's/^allowed_users=.*/allowed_users=console/' "${ROOTFS_DIR}/etc/X11/Xwrapper.config"
fi

install -d "${ROOTFS_DIR}/etc/systemd/journald.conf.d"
cat > "${ROOTFS_DIR}/etc/systemd/journald.conf.d/kiosk.conf" <<EOF
[Journal]
SystemMaxUse=50M
EOF

# Equivalent of `systemctl mask` in a non-running chroot: mask is just a
# symlink to /dev/null.
ln -sf /dev/null "${ROOTFS_DIR}/etc/systemd/system/NetworkManager-wait-online.service"
