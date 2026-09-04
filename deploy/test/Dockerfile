# A plain Debian Bookworm container standing in for a Raspberry Pi OS
# install, so deploy/install.sh's apt installs, group/profile/xinitrc
# handling, and unit-file writes can be exercised end-to-end without
# touching real hardware or the dev machine. Built/run by
# deploy/test-local-install.sh.
#
# There's no init system running here (unlike a real Pi), so systemctl is
# stubbed out - see systemctl-stub.sh. The systemd *integration* itself
# (autologin actually working, unit masking taking effect) can only be
# proven on real hardware; see the Verification section of
# docs/pi-kiosk-plan.md for that.
FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends sudo ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash tester && \
    echo "tester ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/tester && \
    chmod 0440 /etc/sudoers.d/tester

COPY systemctl-stub.sh /usr/local/bin/systemctl
RUN chmod +x /usr/local/bin/systemctl

CMD ["sleep", "infinity"]
