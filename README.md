# Tele JroNex

Terminal-only, direct P2P messaging + file transfer over the internet between two machines.
No central server, no cloud. A systemd background listener handles incoming data;
`tjx` is the interactive terminal client.

```
        INTERNET
           │
      Direct TCP/TLS
        ┌───┴───┐
        │       │
    JroNex SP  JroNex MB
```

---

## Requirements

- Linux (Fedora first)
- Python 3.11+ (`python3`)
- `openssl`
- Each machine: a public IP (or port forwarding), a dedicated port (default `45821`)

---

## Quick start (zero-config install)

The repo already contains the shared credentials (IPs, port `45821`, shared key,
and a shared TLS keypair), so installing is the only step:

```bash
git clone https://github.com/jronexgroup/Tele-JroNex.git
cd Tele-JroNex
./install.sh
```

The installer detects which machine it is (hostname `Rubai` → SP, hostname `fedora` → MB),
writes the right `~/.config/tele-jronex/config.toml`, installs the cert/key/peer cert,
creates `~/Downloads/JroNex-Bro/`, and installs the systemd service.

If hostname detection fails:

```bash
TJX_SIDE=SP ./install.sh   # on your machine
TJX_SIDE=MB ./install.sh   # on your brother's machine
```

Then:

```bash
tjx test
```

Expect `Connection: OK`, `Authentication: OK`, `Tele JroNex: READY`.

Both machines also need TCP port `45821` forwarded through their routers and allowed
in the firewall (see "Router / firewall" below).

---

## Manual configuration (only if you change IPs / credentials)

The installer writes `~/.config/tele-jronex/config.toml` for you.
Typical layout:

```toml
[peer]
name = "MB"
public_ip = "42.105.195.103"
port = 45821
fingerprint = "4c6031bd..."
cert_path = "~/.config/tele-jronex/peer_cert.pem"

[local]
name = "SP"
port = 45821
cert_path = "~/.config/tele-jronex/cert.pem"
key_path = "~/.config/tele-jronex/key.pem"

[transfer]
max_file_size_mb = 200
download_directory = "~/Downloads/JroNex-Bro"

[security]
shared_key = "..."
enforce_peer_ip = false

[network]
connect_timeout = 8
```

## Router / firewall (both machines)

If both machines are behind their own router:

1. On his router: forward **TCP 45821** → his PC's LAN IP:45821.
2. On your router: same for yours.
3. OS firewall (Fedora, when used):

   ```bash
   sudo firewall-cmd --permanent --add-port=45821/tcp
   sudo firewall-cmd --reload
   ```

---

## Test the connection

On either machine:

```bash
tjx test
```

Expected:

```text
Tele JroNex Connectivity Test

Local listener     : ONLINE
Local port         : 45821
Peer               : MB
Peer IP            : xxx.xxx.xxx.xxx
Peer port          : 45821

Connection         : OK
Authentication     : OK

Tele JroNex        : READY
```

If `Connection: FAILED`, check:

- Peer PC is on and `tjx status` shows ONLINE
- Port forwarding is set up on both routers
- Firewall allows TCP 45821
- Public IPs are correct / haven't changed

---

## Use it

```bash
tjx
```

You get:

```text
Tele JroNex
Direct P2P Link
────────────────────────────
JroNex@SP ~
> 
```

- Type a message + Enter → sends to your brother.
- Type (or paste) an existing file path, e.g. `/home/rubai/Videos/test.mp4` → sends the file.
- Received files land in `~/Downloads/JroNex-Bro/`.
- Max file size: 200 MB (change `max_file_size_mb`).
- `/quit` or Ctrl-C exits.

Other commands:

```bash
tjx status     # listener + peer status
tjx config     # show config
tjx test       # connectivity test
tjx version
```

---

## Service management

```bash
systemctl --user status tele-jronex.service
systemctl --user restart tele-jronex.service
systemctl --user stop tele-jronex.service
journalctl --user -u tele-jronex.service -f
```

The service starts automatically at login. To start it before login (boot), lingering is enabled at install (`loginctl enable-linger $USER`).

---

## Uninstall

```bash
cd Tele-JroNex
./uninstall.sh
```

Config/history are kept in `~/.config/tele-jronex/` and `~/.local/share/tele-jronex/`.
Delete those folders manually for a full removal.

---

## How it works (short)

1. `tele-jronex.service` listens on the dedicated port.
2. `tjx` connects to the peer over **mutual TLS** (each side presents its own cert; both verify the pinned peer cert).
3. A HELLO handshake then proves both share the same `shared_key`.
4. Frames carry `MESSAGE`, `FILE_REQUEST`, `FILE_DATA`, ... after that.
5. Files are checked with SHA-256 before being saved.
6. Incoming messages/files are pushed to any open `tjx` via a local socket; history is kept in `~/.local/share/tele-jronex/history.jsonl`.
