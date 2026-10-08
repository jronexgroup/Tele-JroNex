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

## 1. Install on your machine (SP)

```bash
cd Tele-JroNex
./install.sh
```

The installer will:

1. Check Linux / Python / openssl.
2. Copy sources to `~/.local/lib/tele-jronex/`.
3. Create `~/.config/tele-jronex/config.toml`.
4. Generate a TLS keypair in `~/.config/tele-jronex/`.
5. Create `~/Downloads/JroNex-Bro/`.
6. Install + enable `tele-jronex.service` (systemd user service, lingering).
7. Print your certificate fingerprint.

If the installer prints `Permission denied` for the systemd service or `~/.local/bin`, run:

```bash
sudo chown -R $USER:$USER ~/.config/systemd ~/.local/bin
cd Tele-JroNex && ./install.sh
```

Verify:

```bash
tjx version        # Tele JroNex 1.0.0
tjx status         # Listener should show ONLINE
```

---

## 2. Install on your brother's machine (MB)

Copy the whole `Tele-JroNex` folder to his machine (USB, scp, etc.), then:

```bash
cd Tele-JroNex
./install.sh
```

Same sudo fix if needed:

```bash
sudo chown -R $USER:$USER ~/.config/systemd ~/.local/bin
cd Tele-JroNex && ./install.sh
```

Verify:

```bash
tjx version
tjx status
```

---

## 3. Exchange connection info (do both sides)

On **each** machine, run the installer output or:

```bash
openssl x509 -in ~/.config/tele-jronex/cert.pem -outform DER | sha256sum
```

This is your **fingerprint**.

Also note:

- Your **public IP** (`curl ifconfig.me` or check router WAN page)
- The **port** for Tele JroNex (default `45821`)

Send your brother: your public IP, port, fingerprint, and the file
`~/.config/tele-jronex/cert.pem`.

He does the same for you.

---

## 4. Configure each machine

### On your machine (SP)

```bash
nano ~/.config/tele-jronex/config.toml
```

```toml
[peer]
name = "MB"
public_ip = "HIS_PUBLIC_IP"
port = 45821
fingerprint = "HIS_SHA256_FINGERPRINT"
cert_path = "/home/rubai/.config/tele-jronex/peer_cert.pem"

[local]
name = "SP"
port = 45821

[transfer]
max_file_size_mb = 200
download_directory = "/home/rubai/Downloads/JroNex-Bro"

[security]
shared_key = "ONE_LONG_RANDOM_SECRET_YOU_BOTH_SHARE"
enforce_peer_ip = false

[network]
connect_timeout = 8
```

### On his machine (MB)

```bash
nano ~/.config/tele-jronex/config.toml
```

```toml
[peer]
name = "SP"
public_ip = "YOUR_PUBLIC_IP"
port = 45821
fingerprint = "YOUR_SHA256_FINGERPRINT"
cert_path = "/home/BROTHER_USER/.config/tele-jronex/peer_cert.pem"

[local]
name = "MB"
port = 45821

[transfer]
max_file_size_mb = 200
download_directory = "/home/BROTHER_USER/Downloads/JroNex-Bro"

[security]
shared_key = "ONE_LONG_RANDOM_SECRET_YOU_BOTH_SHARE"
enforce_peer_ip = false

[network]
connect_timeout = 8
```

Both sides must use:

- the **same `shared_key`**
- the other's **cert fingerprint**
- the other's **actual public IP + their listening port**

Each side saves his received `cert.pem` as:

```bash
cp <received cert.pem> ~/.config/tele-jronex/peer_cert.pem
```

---

## 5. Router / firewall (both machines)

If both machines are behind their own router:

1. On his router: forward **TCP 45821** → his PC's LAN IP:45821.
2. On your router: same for yours.
3. OS firewall (Fedora, when used):

   ```bash
   sudo firewall-cmd --permanent --add-port=45821/tcp
   sudo firewall-cmd --reload
   ```

---

## 6. Test the connection

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

## 7. Use it

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
