import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import protocol
import transfer

HISTORY_LOCK = threading.Lock()
SUBSCRIBERS = set()
SUB_LOCK = threading.Lock()


def log_history(event):
    event = dict(event)
    event["ts"] = int(time.time())
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY_LOCK, open(config.HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass


def broadcast(event):
    log_history(event)
    data = (json.dumps(event) + "\n").encode("utf-8")
    with SUB_LOCK:
        dead = []
        for s in SUBSCRIBERS:
            try:
                s.sendall(data)
            except OSError:
                dead.append(s)
        for s in dead:
            SUBSCRIBERS.discard(s)
            try:
                s.close()
            except OSError:
                pass


def broker_loop():
    try:
        if config.BROKER_PATH.exists():
            config.BROKER_PATH.unlink()
    except OSError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(str(config.BROKER_PATH))
    os.chmod(config.BROKER_PATH, 0o600)
    srv.listen(8)
    while True:
        conn, _ = srv.accept()
        with SUB_LOCK:
            SUBSCRIBERS.add(conn)


def local_name(cfg):
    return cfg.get("local", {}).get("name", "SP")


def handle_connection(conn, addr, cfg):
    try:
        cert = cfg["local"].get("cert_path", str(config.CONFIG_DIR / "cert.pem"))
        key = cfg["local"].get("key_path", str(config.CONFIG_DIR / "key.pem"))
        peer_cert = cfg.get("peer", {}).get("cert_path", str(config.CONFIG_DIR / "peer_cert.pem"))
        ctx = protocol.tls_context_server(cert, key, peer_cert)
        try:
            tls = ctx.wrap_socket(conn, server_side=True)
        except Exception:
            return
        if not protocol.peer_cert_matches(tls, cfg.get("peer", {}).get("fingerprint", "")):
            protocol.send_frame(tls, protocol.ERROR, reason="unknown peer certificate")
            return
        shared = cfg.get("security", {}).get("shared_key", "")
        try:
            peer_name = protocol.handshake_server(tls, local_name(cfg), shared)
        except protocol.ProtocolError:
            return

        if cfg.get("security", {}).get("enforce_peer_ip", False):
            if addr[0] != cfg.get("peer", {}).get("public_ip"):
                protocol.send_frame(tls, protocol.ERROR, reason="source IP not allowed")
                return

        max_size = config.max_file_size(cfg)
        while True:
            try:
                header, payload = protocol.recv_frame(tls)
            except (protocol.ProtocolError, socket.timeout, ssl.SSLError, ConnectionResetError, BrokenPipeError):
                return
            t = header.get("t")
            if t == protocol.MESSAGE:
                text = header.get("text", "")
                broadcast({"t": "message", "from": peer_name, "text": text})
            elif t == protocol.FILE_REQUEST:
                handle_file_request(tls, cfg, peer_name, header, max_size)
            elif t == protocol.PING:
                protocol.send_frame(tls, protocol.PONG)
            elif t == protocol.ERROR:
                return
            elif t is None:
                return
    finally:
        try:
            conn.close()
        except OSError:
            pass


def handle_file_request(tls, cfg, peer_name, header, max_size):
    filename = os.path.basename(header.get("filename", "file"))
    size = int(header.get("size", 0))
    expected_sha = header.get("sha256", "")
    if size < 0 or size > max_size:
        protocol.send_frame(
            tls,
            protocol.FILE_REJECT,
            reason=f"file exceeds {max_size // (1024 * 1024)} MB limit",
        )
        return
    download = config.download_dir(cfg)
    try:
        tmp = transfer.temp_receive_path(download, filename)
    except OSError:
        protocol.send_frame(tls, protocol.FILE_REJECT, reason="cannot write download directory")
        return
    protocol.send_frame(tls, protocol.FILE_ACCEPT)
    writer = transfer.HashWriter(tmp)
    received = 0
    ok = True
    try:
        while received < size:
            h2, p = protocol.recv_frame(tls)
            if h2.get("t") == protocol.ERROR:
                ok = False
                break
            if h2.get("t") != "FILE_DATA":
                ok = False
                break
            writer.write(p)
            received += len(p)
    except (protocol.ProtocolError, socket.timeout, ssl.SSLError, ConnectionResetError, BrokenPipeError):
        ok = False
    if not ok or received != size:
        writer.abort()
        try:
            protocol.send_frame(tls, protocol.FILE_RESULT, ok=False, reason="incomplete transfer")
        except OSError:
            pass
        broadcast({"t": "file_failed", "from": peer_name, "filename": filename})
        return
    digest = writer.close()
    if expected_sha and digest != expected_sha:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        protocol.send_frame(tls, protocol.FILE_RESULT, ok=False, reason="checksum mismatch")
        broadcast({"t": "file_failed", "from": peer_name, "filename": filename, "reason": "checksum mismatch"})
        return
    target = transfer.safe_download_path(download, filename)
    os.replace(tmp, target)
    protocol.send_frame(tls, protocol.FILE_RESULT, ok=True)
    broadcast(
        {
            "t": "file",
            "from": peer_name,
            "filename": os.path.basename(str(target)),
            "path": str(target),
            "size": size,
        }
    )


def main():
    config.ensure_dirs()
    cfg = config.load_config()
    if not cfg:
        print(f"[tjx] no config found at {config.CONFIG_PATH}")
        print("Run install.sh first (it creates the config).")
        sys.exit(1)
    threading.Thread(target=broker_loop, daemon=True).start()
    port = int(cfg.get("local", {}).get("port", 45821))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(16)
    print(f"[tjx] Tele JroNex listener on port {port}")
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_connection, args=(conn, addr, cfg), daemon=True).start()


if __name__ == "__main__":
    main()
