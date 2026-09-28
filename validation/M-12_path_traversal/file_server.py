"""Minimal file-serving helper — reads files from a configured base directory."""
import os


BASE_DIR = "/var/www/files"


def read_file(filename: str) -> bytes:
    path = os.path.join(BASE_DIR, filename)   # filename may contain ../
    with open(path, "rb") as f:
        return f.read()


def write_file(filename: str, data: bytes) -> None:
    path = os.path.join(BASE_DIR, filename)   # same — no realpath check
    with open(path, "wb") as f:
        f.write(data)


def delete_file(filename: str) -> bool:
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def list_files(subdir: str = "") -> list[str]:
    target = os.path.join(BASE_DIR, subdir)   # subdir not validated
    return os.listdir(target)
