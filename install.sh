#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$HOME/.local/lib/tele-jronex"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/tele-jronex"
DATA_DIR="$HOME/.local/share/tele-jronex"
RUNTIME_DIR="$HOME/.cache/tele-jronex"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "==> Tele JroNex installer"

if [[ "$(uname)" != "Linux" ]]; then
  echo "ERROR: Linux required."; exit 1
fi

for dep in python3 openssl; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    echo "ERROR: missing dependency: $dep"
    echo "Install it with: sudo dnf install $dep   (or use your distro package manager)"
    exit 1
  fi
done

python3 -c "import ssl, tomllib, termios" || { echo "ERROR: Python 3.11+ required."; exit 1; }

echo "==> Installing files to $LIB_DIR"
mkdir -p "$LIB_DIR" "$CONFIG_DIR" "$DATA_DIR" "$RUNTIME_DIR" "$SYSTEMD_USER_DIR"
cp "$SRC_DIR"/src/*.py "$LIB_DIR"/
cp "$SRC_DIR"/src/tjx "$LIB_DIR"/tjx
chmod +x "$LIB_DIR/tjx"
if [[ -w "$HOME/.local/bin" || ! -e "$HOME/.local/bin" ]]; then
  mkdir -p "$HOME/.local/bin"
  ln -sf "$LIB_DIR/tjx" "$HOME/.local/bin/tjx"
fi
TARGET_BIN="$HOME/.local/bin"
if [[ ! -e "$HOME/.local/bin/tjx" ]]; then
  mkdir -p "$HOME/bin"
  ln -sf "$LIB_DIR/tjx" "$HOME/bin/tjx"
  TARGET_BIN="$HOME/bin"
fi
if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  sudo ln -sf "$LIB_DIR/tjx" /usr/local/bin/tjx || true
fi

if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
  echo "==> Creating default config at $CONFIG_DIR/config.toml"
  sed "s|~/Downloads/JroNex-Bro|$HOME/Downloads/JroNex-Bro|" "$SRC_DIR/config/default.toml" > "$CONFIG_DIR/config.toml"
else
  echo "==> Keeping existing config.toml"
fi

mkdir -p "$HOME/Downloads/JroNex-Bro"

if [[ ! -f "$CONFIG_DIR/cert.pem" || ! -f "$CONFIG_DIR/key.pem" ]]; then
  echo "==> Generating TLS keypair"
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CONFIG_DIR/key.pem" -out "$CONFIG_DIR/cert.pem" \
    -days 3650 -subj "/CN=tele-jronex" 2>/dev/null
  chmod 600 "$CONFIG_DIR/key.pem"
fi

FP=$(openssl x509 -in "$CONFIG_DIR/cert.pem" -outform DER | sha256sum | awk '{print $1}')
echo "==> Your certificate fingerprint (SHA-256, add this to your peer's config as peer.fingerprint):"
echo "    $FP"
python3 - "$CONFIG_DIR/config.toml" "$FP" <<'PYEOF'
import re, sys
path, fp = sys.argv[1], sys.argv[2]
text = open(path).read()
if 'cert_fingerprint = ""' in text:
    text = text.replace('cert_fingerprint = ""', f'cert_fingerprint = "{fp}"', 1)
    open(path, "w").write(text)
PYEOF

if command -v systemctl >/dev/null 2>&1 && systemctl --user >/dev/null 2>&1; then
  echo "==> Installing systemd user service"
  cp "$SRC_DIR/systemd/tele-jronex.service" "$SYSTEMD_USER_DIR/tele-jronex.service"
  systemctl --user daemon-reload
  systemctl --user enable tele-jronex.service || true
  systemctl --user restart tele-jronex.service || true
  loginctl enable-linger "$USER" 2>/dev/null || true
else
  echo "==> systemctl --user unavailable; start the listener manually:"
  echo "    python3 $LIB_DIR/server.py &"
fi

echo
echo "==> Done. Next steps:"
echo "  1. Edit $CONFIG_DIR/config.toml with the peer's name/IP/port,"
echo "     their cert fingerprint, and a shared key."
echo "  2. Share YOUR fingerprint (above) with the peer."
echo "  3. Run: tjx test"
echo "  4. Make sure $TARGET_BIN is in your PATH ($HOME/bin usually is)."
