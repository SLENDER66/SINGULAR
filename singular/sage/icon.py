"""L'icône de l'app, dessinée ici plutôt que déposée en binaire.

iOS ne veut pas de SVG pour l'icône de l'écran d'accueil : `apple-touch-icon`
doit être un PNG. Plutôt que de committer une image que personne ne pourra
relire ni modifier, elle est calculée -- pixel par pixel, en Python pur, sans
dépendance. Le fichier reste lisible, l'icône reste modifiable, et il n'y a
aucun binaire opaque dans le dépôt.

Le dessin est un anneau : ce que le Sage fait est regarder. Le point au centre
est ce qu'il regarde.
"""
from __future__ import annotations

import struct
import zlib
from functools import lru_cache

BACKGROUND = (11, 13, 16)
RING = (201, 162, 39)
CORE = (233, 213, 150)


def _png(width: int, height: int, pixels: bytes) -> bytes:
    """Un PNG truecolor, sans filtre, sans canal alpha.

    iOS applique lui-même le masque arrondi de l'icône, donc une image pleine
    est ce qu'il attend : un fond transparent afficherait du noir aux angles.
    """
    stride = width * 3
    raw = b"".join(b"\x00" + pixels[row * stride:(row + 1) * stride] for row in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _blend(base: tuple[int, int, int], top: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    alpha = min(max(alpha, 0.0), 1.0)
    return tuple(round(base[index] + (top[index] - base[index]) * alpha) for index in range(3))  # type: ignore[return-value]


def _coverage(distance: float, edge: float, softness: float) -> float:
    """Anti-aliasing : la fraction du pixel couverte par le bord."""
    return min(max((edge - distance) / softness + 0.5, 0.0), 1.0)


@lru_cache(maxsize=8)
def render_icon(size: int) -> bytes:
    """L'icône, à la taille demandée. Mise en cache : elle ne change jamais."""
    if size < 16:
        raise ValueError("une icône plus petite que 16 pixels n'est pas lisible")
    centre = (size - 1) / 2
    softness = size / 128
    ring_outer = size * 0.34
    ring_inner = size * 0.27
    core = size * 0.085

    rows = bytearray()
    for y in range(size):
        for x in range(size):
            distance = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5
            colour = BACKGROUND
            ring_alpha = min(
                _coverage(distance, ring_outer, softness),
                1.0 - _coverage(distance, ring_inner, softness),
            )
            colour = _blend(colour, RING, ring_alpha)
            colour = _blend(colour, CORE, _coverage(distance, core, softness))
            rows.extend(colour)
    return _png(size, size, bytes(rows))


__all__ = ["render_icon"]
