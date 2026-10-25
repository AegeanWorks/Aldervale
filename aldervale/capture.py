"""Headless frame capture: turn a char-cell Screen into a truecolor PNG.

The game is normally only visible in a terminal.  This module renders the same
cells to an image with a small built-in 5x7 font so an automated reviewer (or a
human without a terminal) can see exactly what the renderer produced.  Only the
standard library is used: raw RGB rows are zlib-compressed into a PNG.
"""

import struct
import zlib

from .buffer import unpack_rgb

FONT = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 15),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 2, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 27, 17),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    "a": (0, 0, 14, 1, 15, 17, 15),
    "b": (16, 16, 30, 17, 17, 17, 30),
    "c": (0, 0, 14, 16, 16, 16, 14),
    "d": (1, 1, 15, 17, 17, 17, 15),
    "e": (0, 0, 14, 17, 31, 16, 14),
    "f": (6, 9, 8, 28, 8, 8, 8),
    "g": (0, 0, 15, 17, 15, 1, 14),
    "h": (16, 16, 30, 17, 17, 17, 17),
    "i": (4, 0, 12, 4, 4, 4, 14),
    "j": (2, 0, 6, 2, 2, 18, 12),
    "k": (16, 16, 18, 20, 24, 20, 18),
    "l": (12, 4, 4, 4, 4, 4, 14),
    "m": (0, 0, 26, 21, 21, 21, 21),
    "n": (0, 0, 30, 17, 17, 17, 17),
    "o": (0, 0, 14, 17, 17, 17, 14),
    "p": (0, 0, 30, 17, 30, 16, 16),
    "q": (0, 0, 15, 17, 15, 1, 1),
    "r": (0, 0, 22, 25, 16, 16, 16),
    "s": (0, 0, 15, 16, 14, 1, 30),
    "t": (8, 8, 28, 8, 8, 9, 6),
    "u": (0, 0, 17, 17, 17, 19, 13),
    "v": (0, 0, 17, 17, 17, 10, 4),
    "w": (0, 0, 17, 17, 21, 21, 10),
    "x": (0, 0, 17, 10, 4, 10, 17),
    "y": (0, 0, 17, 17, 15, 1, 14),
    "z": (0, 0, 31, 2, 4, 8, 31),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (31, 2, 4, 2, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    ".": (0, 0, 0, 0, 0, 12, 12),
    ",": (0, 0, 0, 0, 12, 4, 8),
    ":": (0, 12, 12, 0, 12, 12, 0),
    ";": (0, 12, 12, 0, 12, 4, 8),
    "!": (4, 4, 4, 4, 4, 0, 4),
    "?": (14, 17, 1, 2, 4, 0, 4),
    "-": (0, 0, 0, 31, 0, 0, 0),
    "+": (0, 4, 4, 31, 4, 4, 0),
    "=": (0, 0, 31, 0, 31, 0, 0),
    "*": (0, 10, 4, 31, 4, 10, 0),
    "/": (1, 2, 2, 4, 8, 8, 16),
    "\\": (16, 8, 8, 4, 2, 2, 1),
    "|": (4, 4, 4, 4, 4, 4, 4),
    "(": (2, 4, 8, 8, 8, 4, 2),
    ")": (8, 4, 2, 2, 2, 4, 8),
    "[": (14, 8, 8, 8, 8, 8, 14),
    "]": (14, 2, 2, 2, 2, 2, 14),
    "{": (6, 4, 4, 8, 4, 4, 6),
    "}": (12, 4, 4, 2, 4, 4, 12),
    "<": (2, 4, 8, 16, 8, 4, 2),
    ">": (8, 4, 2, 1, 2, 4, 8),
    "'": (4, 4, 0, 0, 0, 0, 0),
    '"': (10, 10, 0, 0, 0, 0, 0),
    "_": (0, 0, 0, 0, 0, 0, 31),
    "#": (10, 10, 31, 10, 31, 10, 10),
    "%": (25, 26, 2, 4, 8, 11, 19),
    "@": (14, 17, 23, 21, 23, 16, 14),
    "&": (12, 18, 20, 8, 21, 18, 13),
    "$": (4, 15, 20, 14, 5, 30, 4),
    "~": (0, 0, 8, 21, 2, 0, 0),
    "^": (4, 10, 17, 0, 0, 0, 0),
    "`": (8, 4, 0, 0, 0, 0, 0),
}
GLYPH_W = 5
GLYPH_H = 7
CELL_W = GLYPH_W + 1
CELL_H = GLYPH_H + 1
BG = (8, 10, 16)


def _scaled(color, factor):
    r, g, b = unpack_rgb(color)
    return (int(r * factor), int(g * factor), int(b * factor))


def _blend(base, over, alpha):
    return (int(base[0] + (over[0] - base[0]) * alpha),
            int(base[1] + (over[1] - base[1]) * alpha),
            int(base[2] + (over[2] - base[2]) * alpha))


def _cell_bytes(ch, color, scale, cache):
    key = (ch, color, scale)
    cached = cache.get(key)
    if cached is not None:
        return cached
    ink = _scaled(color, 1.0)
    bg = _blend(BG, _scaled(color, 0.45), 0.55)
    mask = FONT.get(ch, FONT["?"])
    rows = []
    for gy in range(CELL_H):
        bits = mask[gy] if gy < GLYPH_H else 0
        line = bytearray()
        for gx in range(CELL_W):
            on = gx < GLYPH_W and (bits >> (GLYPH_W - 1 - gx)) & 1
            line.extend(ink * scale if on else bg * scale)
        block = bytes(line)
        rows.extend([block] * scale)
    cached = tuple(rows)
    cache[key] = cached
    return cached


def screen_pixels(screen, scale=2):
    """Return (width, height, rgb_bytes) for a Screen at the given cell scale."""
    scale = max(1, int(scale))
    cw = CELL_W * scale
    subrows = CELL_H * scale
    width = screen.w * cw
    height = screen.h * subrows
    cache = {}
    out = bytearray()
    for y in range(screen.h):
        chars = screen.chars[y]
        fg = screen.fg[y]
        row = [bytearray() for _ in range(subrows)]
        for x in range(screen.w):
            cell = _cell_bytes(chars[x], fg[x], scale, cache)
            for i in range(subrows):
                row[i].extend(cell[i])
        for line in row:
            out.extend(line)
    return width, height, bytes(out)


def _chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload +
            struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def png_bytes(width, height, rgb_rows):
    """Encode raw RGB scanlines (no filter byte) as a PNG byte string."""
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(rgb_rows[start:start + stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" +
            _chunk(b"IHDR", header) +
            _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            _chunk(b"IEND", b""))


def save_png(path, screen, scale=2):
    """Write a Screen to a truecolor PNG; return (width, height)."""
    width, height, rgb_rows = screen_pixels(screen, scale=scale)
    with open(path, "wb") as f:
        f.write(png_bytes(width, height, rgb_rows))
    return width, height
