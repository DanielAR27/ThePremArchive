from __future__ import annotations

import hashlib

_BITS = 64
_BANDS = 4
_BAND_BITS = _BITS // _BANDS
_BAND_MASK = (1 << _BAND_BITS) - 1
_SHINGLE_SIZE = 4
_MAX_SHINGLES = 4000


def content_hash(text: str) -> str:
    """Politica 5 (duplicado exacto): huella del texto normalizado."""
    return hashlib.sha256(" ".join(text.split()).lower().encode()).hexdigest()


def simhash(words: list[str]) -> int:
    """Politica 5 (casi-duplicado): SimHash de 64 bits sobre shingles de 4 palabras."""
    if len(words) < _SHINGLE_SIZE:
        return 0

    vector = [0] * _BITS
    for i in range(min(len(words) - _SHINGLE_SIZE + 1, _MAX_SHINGLES)):
        shingle = " ".join(words[i:i + _SHINGLE_SIZE]).encode()
        digest = int.from_bytes(hashlib.blake2b(shingle, digest_size=8).digest(), "big")
        for bit in range(_BITS):
            vector[bit] += 1 if (digest >> bit) & 1 else -1

    return sum(1 << bit for bit in range(_BITS) if vector[bit] > 0)


def bands(value: int) -> list[tuple[int, int]]:
    """Divide el simhash en bandas para indexarlo y buscar candidatos en O(1)."""
    return [(b, (value >> (b * _BAND_BITS)) & _BAND_MASK) for b in range(_BANDS)]


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def to_signed(value: int) -> int:
    """SQLite solo almacena enteros con signo de 64 bits."""
    return value - (1 << 64) if value >= (1 << 63) else value


def from_signed(value: int) -> int:
    return value + (1 << 64) if value < 0 else value
