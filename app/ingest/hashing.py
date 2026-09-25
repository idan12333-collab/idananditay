"""Exact (SHA-256) and perceptual (pHash/dHash) hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import imagehash
from PIL import Image

_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def perceptual_hashes(img: Image.Image) -> tuple[str, str]:
    """64-bit pHash and dHash as 16-char hex strings."""
    return str(imagehash.phash(img, hash_size=8)), str(imagehash.dhash(img, hash_size=8))


def hex_to_int(h: str) -> int:
    return int(h, 16)


def hamming(a: str, b: str) -> int:
    return (hex_to_int(a) ^ hex_to_int(b)).bit_count()
