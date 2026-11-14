"""APXS X-ray spectra (MSL *rsp*.csv and CSA calibration spectra)."""
from __future__ import annotations

from pathlib import Path

from .chemistry import XRAY_LINES
from .net import http_get


def parse_spectrum(text: str) -> dict:
    """Two-column CSV: energy (eV), counts. The first data channel holds the counting time (s)."""
    lines = [l for l in text.splitlines() if l.strip()]
    title = ""
    if lines and not lines[0].strip()[:1].isdigit():
        title = lines[0].strip().strip('"').strip()
        lines = lines[1:]
    energy, counts = [], []
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            e, c = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        energy.append(e)
        counts.append(c)
    live_time = counts[0] if counts else None
    energy, counts = energy[1:], counts[1:]
    kev = [round(e / 1000, 4) for e in energy]
    lo, hi = (kev[0], kev[-1]) if kev else (0, 0)
    lines_in_range = {el: e for el, e in XRAY_LINES.items() if lo <= e <= hi}
    return {"title": title, "live_time_s": live_time, "energy_kev": kev, "counts": counts, "lines": lines_in_range}


def load_spectrum(local: Path | None, url: str | None, cache_dir: Path) -> dict:
    """Read from the raw download if present, else the on-disk cache, else download once."""
    if local is not None and local.exists():
        return parse_spectrum(local.read_text(errors="replace"))
    if not url:
        raise FileNotFoundError("no spectrum available")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / url.rsplit("/", 1)[-1]
    if not cached.exists():
        cached.write_bytes(http_get(url, timeout=20))
    return parse_spectrum(cached.read_text(errors="replace"))
