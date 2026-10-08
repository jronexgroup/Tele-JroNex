import os
import socket
import ssl
import sys
import termios
import threading
import time
import tty
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import protocol
import transfer

import json


def ui_print_line(text, history=False):
    prefix = ""
    sys.stdout.write("\r\033[K" + prefix + text + "\n")
    sys.stdout.flush()


class Editor:
    def __init__(self):
        self.buffer = ""
        self.lock = threading.RLock()
        self.on_submit = None

    def display(self):
        with self.lock:
            sys.stdout.write("\r\033[K> " + self.buffer)
            sys.stdout.flush()

    def wrap_print(self, text):
        with self.lock:
            sys.stdout.write("\r\033[K" + text + "\n> " + self.buffer)
            sys.stdout.flush()

    def run(self):
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            self.display()
            while True:
                ch = sys.stdin.read(1)
                with self.lock:
                    if ch in ("\r", "\n"):
                        line = self.buffer
                        self.buffer = ""
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        if self.on_submit:
                            self.on_submit(line)
                        self.display()
                    elif ch in ("\x7f", "\x08"):
                        self.buffer = self.buffer[:-1]
                        self.display()
                    elif ch == "\x03":
                        raise KeyboardInterrupt
                    elif ch == "\x04":
                        raise EOFError
                    elif ch == "\x1b":
                        sys.stdin.read(2)
                    elif ch >= " ":
                        self.buffer += ch
                        self.display()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def subscribe_broker(editor):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(str(config.BROKER_PATH))
        f = s.makefile("r", encoding="utf-8")
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            show_event(editor, ev, from_history=False)
    except (OSError, ConnectionRefusedError):
        return


def show_event(editor, ev, from_history):
    t = ev.get("t")
    src = ev.get("from", "?")
    if t == "message":
        editor.wrap_print(f"JroNex@{src}: {ev.get('text','')}")
    elif t == "file":
        editor.wrap_print(f"JroNex@{src} sent: {ev.get('filename','?')}")
        editor.wrap_print(f"Saved to: {ev.get('path','?')}")
    elif t == "file_failed":
        editor.wrap_print(f"[JroNex] File from {src} failed ({ev.get('reason','incomplete')})")


def print_history(editor, n=20):
    try:
        lines = Path(config.HISTORY_PATH).read_text(encoding="utf-8").strip().splitlines()
    except (OSError, FileNotFoundError):
        return
    for line in lines[-n:]:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("t")
        if t == "message":
            editor.wrap_print(f"[history] JroNex@{ev.get('from','?')}: {ev.get('text','')}")
        elif t == "file":
            editor.wrap_print(f"[history] {ev.get('from','?')} sent {ev.get('filename','?')}")


def connect_peer(cfg, services=None):
    peer_ip = cfg["peer"]["public_ip"]
    peer_port = int(cfg["peer"]["port"])
    timeout = int(cfg.get("network", {}).get("connect_timeout", 8))
    raw = socket.create_connection((peer_ip, peer_port), timeout=timeout)
    cert = cfg["local"].get("cert_path", str(config.CONFIG_DIR / "cert.pem"))
    key = cfg["local"].get("key_path", str(config.CONFIG_DIR / "key.pem"))
    peer_cert = cfg["peer"].get("cert_path", str(config.CONFIG_DIR / "peer_cert.pem"))
    ctx = protocol.tls_context_client(cert, key, peer_cert)
    tls = ctx.wrap_socket(raw, server_hostname=peer_ip)
    if not protocol.peer_cert_matches(tls, cfg["peer"].get("fingerprint", "")):
        tls.close()
        raise protocol.ProtocolError("peer certificate fingerprint mismatch")
    name = cfg["local"]["name"]
    shared = cfg.get("security", {}).get("shared_key", "")
    protocol.handshake_client(tls, name, shared, peer_name=cfg["peer"].get("name"))
    tls.settimeout(60)
    return tls


def log_history(event):
    event = dict(event)
    event["ts"] = int(time.time())
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass


def send_message(cfg, text, editor):
    try:
        tls = connect_peer(cfg)
    except (OSError, socket.timeout, ssl.SSLError, protocol.ProtocolError, KeyError) as e:
        editor.wrap_print("[JroNex] ERROR: Peer is unreachable.")
        return False
    try:
        protocol.send_frame(tls, protocol.MESSAGE, text=text)
    except OSError:
        editor.wrap_print("[JroNex] ERROR: Failed to send.")
        return False
    finally:
        try:
            tls.close()
        except OSError:
            pass
    log_history({"t": "message", "from": cfg.get("local", {}).get("name", "?"), "text": text, "out": True})
    return True


def send_file(cfg, path, editor):
    p = Path(os.path.expanduser(path.strip().strip('"').strip("'")))
    if not p.is_file():
        return False
    size = p.stat().st_size
    limit = config.max_file_size(cfg)
    editor.wrap_print(f"Sending: {p.name}")
    editor.wrap_print(f"Size: {transfer.human_size(size)}")
    if size > limit:
        editor.wrap_print(f"[JroNex] ERROR: File exceeds {limit // (1024*1024)} MB limit.")
        return True
    try:
        tls = connect_peer(cfg)
    except (OSError, socket.timeout, ssl.SSLError, protocol.ProtocolError, KeyError):
        editor.wrap_print("[JroNex] ERROR: Unable to connect to peer.")
        editor.wrap_print("File was not sent.")
        return True
    try:
        digest = transfer.sha256_file(p)
        protocol.send_frame(
            tls,
            protocol.FILE_REQUEST,
            filename=p.name,
            size=size,
            sha256=digest,
        )
        header, _ = protocol.recv_frame(tls)
        if header.get("t") == protocol.FILE_REJECT:
            editor.wrap_print(f"[JroNex] Rejected: {header.get('reason','?')}")
            return True
        if header.get("t") != protocol.FILE_ACCEPT:
            editor.wrap_print("[JroNex] ERROR: Unexpected response from peer.")
            return True
        sent = 0
        with open(p, "rb") as f:
            while True:
                chunk = f.read(transfer.CHUNK)
                if not chunk:
                    break
                protocol.send_frame(tls, "FILE_DATA", payload=chunk)
                sent += len(chunk)
                pct = int(sent * 100 / max(size, 1))
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                sys.stdout.write(f"\r\033[KSending {p.name} {bar} {pct}%")
                sys.stdout.flush()
        sys.stdout.write("\n")
        header, _ = protocol.recv_frame(tls)
        if header.get("t") == protocol.FILE_RESULT and header.get("ok"):
            editor.wrap_print("[JroNex] File sent successfully.")
        else:
            editor.wrap_print(f"[JroNex] ERROR: {header.get('reason','send failed')}")
    except (OSError, socket.timeout, ssl.SSLError, protocol.ProtocolError, BrokenPipeError) as e:
        editor.wrap_print(f"[JroNex] ERROR: {e}")
        editor.wrap_print("File was not sent.")
    finally:
        try:
            tls.close()
        except OSError:
            pass
    return True


def run_client():
    cfg = config.load_config()
    if not cfg:
        print(f"[tjx] no config found at {config.CONFIG_PATH}")
        sys.exit(1)
    name = cfg.get("local", {}).get("name", "SP")
    editor = Editor()

    def on_submit(line):
        line = line.strip()
        if not line:
            editor.display()
            return
        if line.lower() in ("/quit", "/exit"):
            raise SystemExit
        if send_file(cfg, line, editor):
            return
        send_message(cfg, line, editor)

    editor.on_submit = on_submit
    print(f"Tele JroNex")
    print("Direct P2P Link")
    print("────────────────────────────")
    print(f"JroNex@{name} ~")
    threading.Thread(target=subscribe_broker, args=(editor,), daemon=True).start()
    print_history(editor)
    try:
        editor.run()
    except (KeyboardInterrupt, EOFError, SystemExit):
        print()


if __name__ == "__main__":
    run_client()
