import hashlib
import json
import socket
import ssl
import struct

VERSION = 1
APP = "tjx"

HELLO = "HELLO"
HELLO_ACK = "HELLO_ACK"
MESSAGE = "MESSAGE"
FILE_REQUEST = "FILE_REQUEST"
FILE_ACCEPT = "FILE_ACCEPT"
FILE_REJECT = "FILE_REJECT"
FILE_RESULT = "FILE_RESULT"
ERROR = "ERROR"
PING = "PING"
PONG = "PONG"


class ProtocolError(Exception):
    pass


def _recv_exactly(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ProtocolError("connection closed")
        buf.extend(chunk)
    return bytes(buf)


def send_frame(sock, ftype, payload=b"", **fields):
    header = {"t": ftype, "v": VERSION, "payload_size": len(payload), **fields}
    h = json.dumps(header).encode("utf-8")
    sock.sendall(struct.pack("!I", len(h)) + h + payload)


def recv_frame(sock, max_header=65536):
    raw = _recv_exactly(sock, 4)
    (hlen,) = struct.unpack("!I", raw)
    if hlen > max_header:
        raise ProtocolError("header too large")
    header = json.loads(_recv_exactly(sock, hlen).decode("utf-8"))
    payload = b""
    plen = header.get("payload_size", 0)
    if plen:
        payload = _recv_exactly(sock, plen)
    return header, payload


def auth_token(shared_key):
    return hashlib.sha256(shared_key.encode("utf-8")).hexdigest()


def handshake_client(sock, name, shared_key, peer_name=None, timeout=8):
    sock.settimeout(timeout)
    send_frame(sock, HELLO, name=name, auth=auth_token(shared_key))
    header, _ = recv_frame(sock)
    if header.get("t") == ERROR:
        raise ProtocolError(header.get("reason", "handshake failed"))
    if header.get("t") != HELLO_ACK:
        raise ProtocolError("bad handshake response")
    if header.get("auth") != auth_token(shared_key):
        raise ProtocolError("peer authentication failed")
    if peer_name and header.get("name") != peer_name:
        raise ProtocolError(f"unexpected peer name: {header.get('name')}")
    return header.get("name")


def handshake_server(sock, name, shared_key, timeout=8):
    sock.settimeout(timeout)
    header, _ = recv_frame(sock)
    if header.get("t") != HELLO:
        send_frame(sock, ERROR, reason="expected HELLO")
        raise ProtocolError("expected HELLO")
    if header.get("auth") != auth_token(shared_key):
        send_frame(sock, ERROR, reason="authentication failed")
        raise ProtocolError("peer authentication failed")
    peer_name = header.get("name", "?")
    send_frame(sock, HELLO_ACK, name=name, auth=auth_token(shared_key))
    return peer_name


def tls_context_server(cert_path, key_path, peer_cert_path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    ctx.load_verify_locations(cafile=peer_cert_path)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def tls_context_client(cert_path, key_path, peer_cert_path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.load_cert_chain(cert_path, key_path)
    ctx.load_verify_locations(cafile=peer_cert_path)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def peer_cert_matches(sock, fingerprint_hex):
    if not fingerprint_hex:
        return True
    der = sock.getpeercert(binary_form=True)
    if der is None:
        return False
    return hashlib.sha256(der).hexdigest().lower() == fingerprint_hex.lower().replace(":", "")
