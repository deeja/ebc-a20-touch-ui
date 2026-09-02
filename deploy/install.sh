#!/bin/sh
# Run on the Raspberry Pi, from inside the project directory.
set -e

sudo apt-get update
sudo apt-get install -y python3-tk python3-pip python3-serial

sudo usermod -a -G dialout "$USER"

sudo cp deploy/ebc-tester.service /etc/systemd/system/ebc-tester.service
sudo systemctl daemon-reload
sudo systemctl enable ebc-tester.service

echo "Installed. Log out/in (or reboot) for the dialout group change to take"
echo "effect, then: sudo systemctl start ebc-tester"
