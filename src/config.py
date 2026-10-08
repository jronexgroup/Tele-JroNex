import os
import tomllib
from pathlib import Path

APP = "tele-jronex"

CONFIG_DIR = Path(os.environ.get("TJX_CONFIG_DIR", Path.home() / ".config" / APP))
CONFIG_PATH = CONFIG_DIR / "config.toml"
DATA_DIR = Path(os.environ.get("TJX_DATA_DIR", Path.home() / ".local" / "share" / APP))
HISTORY_PATH = DATA_DIR / "history.jsonl"
RUNTIME_DIR = Path(os.environ.get("TJX_RUNTIME_DIR", Path.home() / ".cache" / APP))
BROKER_PATH = RUNTIME_DIR / "broker.sock"

DEFAULT_CONFIG = """\
[peer]
name = "MB"
public_ip = "127.0.0.1"
port = 45821
fingerprint = ""
cert_path = ""

[local]
name = "SP"
port = 45821
cert_fingerprint = ""

[transfer]
max_file_size_mb = 200
download_directory = "~/Downloads/JroNex-Bro"

[security]
shared_key = "change-me"
enforce_peer_ip = false

[network]
connect_timeout = 8
"""


def load_config():
    cfg = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            cfg = tomllib.load(f)
    return cfg


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def download_dir(cfg):
    p = cfg.get("transfer", {}).get("download_directory", "~/Downloads/JroNex-Bro")
    return Path(os.path.expanduser(p))


def max_file_size(cfg):
    mb = cfg.get("transfer", {}).get("max_file_size_mb", 200)
    return int(mb) * 1024 * 1024
