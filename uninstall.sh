#!/usr/bin/env bash
set -euo pipefail

echo "==> Tele JroNex uninstaller"

systemctl --user disable --now tele-jronex.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/tele-jronex.service"
rm -rf "$HOME/.local/lib/tele-jronex"
rm -f "$HOME/.local/bin/tjx"
if command -v sudo >/dev/null 2>&1; then
  sudo rm -f /usr/local/bin/tjx || true
fi
systemctl --user daemon-reload 2>/dev/null || true

echo "Removed program and service."
echo "Config and history kept in:"
echo "  $HOME/.config/tele-jronex"
echo "  $HOME/.local/share/tele-jronex"
echo "Delete those manually if you want a full removal."
