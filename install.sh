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

SHARED_KEY="54bb9d3bbf203b244a0273bef68059a0aed4f1dd086e8cbe"
PORT="45821"
SP_IP="139.5.230.51"
MB_IP="42.105.195.103"
SP_HOST="Rubai"
MB_HOST="fedora"
FP="4c6031bd3c52d5561629c98df47637ad198d9f515827473d93c9bf7cb115ba68"

HOST="$(hostname)"
SIDE="${TJX_SIDE:-}"
if [[ -z "$SIDE" ]]; then
  case "$HOST" in
    "$SP_HOST") SIDE="SP" ;;
    "$MB_HOST") SIDE="MB" ;;
    *) echo "ERROR: unrecognized hostname '$HOST'."
       echo "Re-run with TJX_SIDE=SP or TJX_SIDE=MB, e.g.:"
       echo "  TJX_SIDE=MB ./install.sh"
       exit 1 ;;
  esac
fi
echo "==> Detected side: $SIDE"

if [[ "$SIDE" == "SP" ]]; then
  LOCAL_NAME="SP"; PEER_NAME="MB"; PEER_IP="$MB_IP"
else
  LOCAL_NAME="MB"; PEER_NAME="SP"; PEER_IP="$SP_IP"
fi

mkdir -p "$HOME/Downloads/JroNex-Bro"
cp "$SRC_DIR/config/embedded/cert.pem" "$CONFIG_DIR/cert.pem"
cp "$SRC_DIR/config/embedded/key.pem" "$CONFIG_DIR/key.pem"
cp "$SRC_DIR/config/embedded/cert.pem" "$CONFIG_DIR/peer_cert.pem"
chmod 600 "$CONFIG_DIR/key.pem"

echo "==> Writing config at $CONFIG_DIR/config.toml"
cat > "$CONFIG_DIR/config.toml" <<EOF
[peer]
name = "$PEER_NAME"
public_ip = "$PEER_IP"
port = $PORT
fingerprint = "$FP"
cert_path = "$CONFIG_DIR/peer_cert.pem"

[local]
name = "$LOCAL_NAME"
port = $PORT
cert_path = "$CONFIG_DIR/cert.pem"
key_path = "$CONFIG_DIR/key.pem"

[transfer]
max_file_size_mb = 200
download_directory = "$HOME/Downloads/JroNex-Bro"

[security]
shared_key = "$SHARED_KEY"
enforce_peer_ip = false

[network]
connect_timeout = 8
EOF

LISTENER_UP=0
if command -v systemctl >/dev/null 2>&1 && systemctl --user >/dev/null 2>&1; then
  echo "==> Installing systemd user service"
  cp "$SRC_DIR/systemd/tele-jronex.service" "$SYSTEMD_USER_DIR/tele-jronex.service" 2>/dev/null || \
    sudo cp "$SRC_DIR/systemd/tele-jronex.service" "$SYSTEMD_USER_DIR/tele-jronex.service" 2>/dev/null || true
  systemctl --user daemon-reload 2>/dev/null || true
  systemctl --user enable tele-jronex.service 2>/dev/null || true
  systemctl --user restart tele-jronex.service 2>/dev/null || true
  loginctl enable-linger "$USER" 2>/dev/null || true
  sleep 1
  if systemctl --user is-active tele-jronex.service 2>/dev/null | grep -q active; then
    LISTENER_UP=1
  fi
fi

if [[ "$LISTENER_UP" != "1" ]]; then
  echo "==> systemd service failed to start; starting listener directly..."
  pkill -f "tele-jronex/server.py" 2>/dev/null || true
  sleep 0.5
  setsid nohup /usr/bin/python3 "$LIB_DIR/server.py" > "$DATA_DIR/listener.log" 2>&1 < /dev/null &
  sleep 1
  if ss -tln 2>/dev/null | grep -q ":45821"; then
    LISTENER_UP=1
    echo "    listener is UP (port 45821)"
  else
    echo "    WARNING: listener did not start; see $DATA_DIR/listener.log"
  fi
fi

echo ==> "Tailscale (needed for NAT/hotspot connectivity)"
if ! command -v tailscale >/dev/null 2>&1; then
  echo "    tailscale not found; installing (sudo may ask for a password)..."
  sudo dnf install tailscale -y || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale || true
fi
if command -v tailscale >/dev/null 2>&1; then
  sudo systemctl enable --now tailscaled 2>/dev/null || true
  if sudo tailscale status >/dev/null 2>&1; then
    echo "    tailscale is up: $(tailscale ip -4 2>/dev/null)"
  else
    echo "    ACTION NEEDED: run  sudo tailscale up"
    echo "    and log in with your browser (same account on both machines)."
  fi
fi

echo
echo "==> Done. This machine is configured as: $SIDE"
echo "  Peer: $PEER_NAME at $PEER_IP:$PORT"
echo "  Run: tjx test      (should show READY once the peer is online)"
echo "  Run: tjx           (chat client)"
echo "  Make sure $TARGET_BIN is in your PATH."
