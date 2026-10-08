import hashlib
import os
import tempfile

CHUNK = 64 * 1024


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_stream_chunks(chunks):
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.hexdigest()


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{n} B"
            return f"{n:.1f} {unit}"
        n /= 1024


def safe_download_path(directory, filename):
    filename = os.path.basename(filename)
    if not filename:
        filename = "download.bin"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    if not target.exists():
        return target
    stem, suffix = os.path.splitext(filename)
    i = 1
    while True:
        candidate = directory / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


class HashWriter:
    def __init__(self, path):
        self._f = open(path, "wb")
        self._h = hashlib.sha256()

    def write(self, data):
        self._f.write(data)
        self._h.update(data)

    def close(self):
        self._f.close()
        return self._h.hexdigest()

    def abort(self):
        try:
            self._f.close()
        finally:
            try:
                os.unlink(self._f.name)
            except OSError:
                pass


def temp_receive_path(directory, filename):
    directory.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".tjx-", dir=str(directory))
    os.close(fd)
    return path
