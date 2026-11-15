"""MGS MOLA elevation from NASA Mars Trek tiles (8-bit DEM), decoded without extra dependencies.

The Trek layer Mars_MGS_MOLA_DEM_mosaic_global_463m_8 stores elevation as grey 0..255 = -8201..+21241 m
(about 115 m per step). Zoom 2 is 8 x 4 tiles of 256 px: 2048 x 1024 px, ~0.18 deg per pixel, equirectangular,
-180..180 E, 90..-90 N."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

DEM_MIN_M, DEM_MAX_M = -8201.0, 21241.0
COLS, ROWS, TILE = 8, 4, 256


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read_png_grey(path: Path, keep_alpha: bool = False) -> list[list]:
    """Decode an 8-bit greyscale (optionally +alpha) PNG into rows of grey values, or (grey, alpha) pairs."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (0, 4) or interlace:
                raise ValueError(f"{path}: unsupported PNG (depth {depth}, colour type {ctype})")
            bpp = 1 if ctype == 0 else 2
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + (0, a, b, (a + b) >> 1, _paeth(a, b, c))[f]) & 0xFF
        if keep_alpha:
            rows.append([(line[i], line[i + 1] if bpp == 2 else 255) for i in range(0, stride, bpp)])
        else:
            rows.append(list(line[::bpp]))
        prev = line
    return rows


def load_dem(folder: Path) -> list[list[float]]:
    """Whole-planet elevation grid in metres (row 0 = 90N, column 0 = 180W)."""
    grid = [[0.0] * (COLS * TILE) for _ in range(ROWS * TILE)]
    for ty in range(ROWS):
        for tx in range(COLS):
            tile = read_png_grey(folder / f"{ty}_{tx}.png")
            for y, row in enumerate(tile):
                g = grid[ty * TILE + y]
                for x, v in enumerate(row):
                    g[tx * TILE + x] = DEM_MIN_M + v / 255 * (DEM_MAX_M - DEM_MIN_M)
    return grid


def elevation_at(grid: list[list[float]], lat: float, lon: float) -> float:
    h, w = len(grid), len(grid[0])
    x = min(w - 1, max(0, int((lon + 180) / 360 * w)))
    y = min(h - 1, max(0, int((90 - lat) / 180 * h)))
    return grid[y][x]


def cell_means(grid: list[list[float]], deg: float = 5.0) -> dict[tuple[float, float], float]:
    """Mean elevation of every deg x deg cell, keyed by its centre (lat, lon) like the GRS tables."""
    h, w = len(grid), len(grid[0])
    out = {}
    for i in range(int(180 / deg)):
        for j in range(int(360 / deg)):
            y0, y1 = int(i * deg / 180 * h), int((i + 1) * deg / 180 * h)
            x0, x1 = int(j * deg / 360 * w), int((j + 1) * deg / 360 * w)
            vals = [grid[y][x] for y in range(y0, y1) for x in range(x0, x1)]
            out[(90 - (i + 0.5) * deg, -180 + (j + 0.5) * deg)] = sum(vals) / len(vals)
    return out
