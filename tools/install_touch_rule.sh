#!/usr/bin/env bash
# tools/install_touch_rule.sh -- let the normal user read the Pi 2's USB touch chip.
#
# The chip (USB id 0eef:0005, "RPI_TOUCH By ZH851") shows up as /dev/hidrawN owned by root, so the clock
# (which runs as your normal user) is not allowed to read it.  This installs ONE udev rule that gives the
# group "input" read access to that chip only.  Run once on the Pi, then unplug/replug or reboot:
#       bash ~/VedicGhadi/tools/install_touch_rule.sh
# Undo:  sudo rm /etc/udev/rules.d/99-vedicghadi-touch.rules ; sudo udevadm control --reload-rules
set -e
RULE=/etc/udev/rules.d/99-vedicghadi-touch.rules
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0eef", ATTRS{idProduct}=="0005", MODE="0660", GROUP="input"' | sudo tee "$RULE" >/dev/null
echo "rule written: $RULE"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw --action=add || true
sleep 1
echo "-- the hidraw devices now:"
ls -l /dev/hidraw* 2>/dev/null || true
if id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
  echo "OK: $USER is in the group 'input'."
else
  echo "NOTE: $USER is NOT in the group 'input'. Run:  sudo usermod -aG input $USER   then log out/in or reboot."
fi
echo "done -- if the touch chip's line above says  crw-rw---- root input  you are set (else: sudo reboot)."
