"""Spectrum lab: match a raw APXS X-ray spectrum against every Curiosity spectrum and the CSA lab standards.

Every spectrum is re-binned onto one energy grid using its own energy calibration (the rsp files give energy
per channel), so spectra from different sols line up. Matching compares the *shape* of the spectra:
square-root counts (which evens out Poisson noise between strong and weak peaks), normalised to unit length,
compared by cosine similarity. The method was chosen by the hold-out test in validate.py.
"""
from __future__ import annotations

import math
import random

from .chemistry import XRAY_LINES

E_MIN, E_MAX, E_STEP = 1.0, 15.0, 0.025          # keV: every element line APXS reports lies in this range
N_BINS = int(round((E_MAX - E_MIN) / E_STEP))
GRID = [round(E_MIN + (i + 0.5) * E_STEP, 4) for i in range(N_BINS)]
# Strong peaks that are not from the rock (Curiosity's calibration-target and instrument lines are excluded
# by construction: only real targets are in the library).
PEAK_HALF_KEV = 0.075


def rebin(energy_kev: list[float], counts: list[float]) -> list[int]:
    """Sum each channel into the 25 eV bin that contains its calibrated energy (counts are conserved)."""
    out = [0.0] * N_BINS
    for e, c in zip(energy_kev, counts):
        i = int((e - E_MIN) / E_STEP)
        if 0 <= i < N_BINS and c > 0:
            out[i] += c
    return [int(round(v)) for v in out]


def shape(binned: list[int]) -> list[float]:
    v = [math.sqrt(max(0, c)) for c in binned]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def to_pct(cos: float) -> int:
    """Cosine of sqrt spectra sits between ~0.9 and 1 for any two APXS spectra; map 0.95..1 onto 0..100%."""
    return max(0, min(100, round((cos - 0.95) / 0.05 * 100)))


def thin(binned: list[int], keep: float, rng: random.Random) -> list[int]:
    """A shorter integration of the same rock: keep each count with probability `keep` (binomial thinning)."""
    out = []
    for c in binned:
        if c > 60:                                   # normal approximation for speed
            k = c * keep + rng.gauss(0, math.sqrt(c * keep * (1 - keep)))
            out.append(max(0, int(round(k))))
        else:
            out.append(sum(1 for _ in range(c) if rng.random() < keep))
    return out


def peaks(binned: list[int]) -> list[dict]:
    """Which element lines stand clearly above the local continuum (counts in the line window vs. the windows
    either side). A screening for the chart labels, not a quantitative analysis."""
    out = []
    w = max(1, int(PEAK_HALF_KEV / E_STEP))
    lines = {**XRAY_LINES, "Ar": 2.957}            # argon K-alpha: from the Martian air between instrument and rock
    for el, e in sorted(lines.items(), key=lambda kv: kv[1]):
        if not E_MIN + 0.1 < e < E_MAX - 0.1:
            continue
        c = int((e - E_MIN) / E_STEP)
        line = sum(binned[max(0, c - w):c + w + 1])
        side = (sum(binned[max(0, c - 3 * w):max(0, c - w)]) + sum(binned[c + w + 1:c + 3 * w + 1])) / 2 or 1
        signif = (line - side) / math.sqrt(line + side + 1)
        out.append({"el": el, "kev": e, "signal": round(line / side, 2), "sigma": round(signif, 1), "detected": signif >= 5,
                    "air": el == "Ar"})
    return out


class SpectrumLibrary:
    def __init__(self, items: list[dict]):
        """items: {id, kind ('rock' | 'ref'), counts (binned), ...metadata}"""
        self.items = items
        self.shapes = [shape(it["counts"]) for it in items]

    def counts_of(self, item_id: str) -> list[int] | None:
        return next((it["counts"] for it in self.items if it["id"] == item_id), None)

    def search(self, binned: list[int], top_k: int = 8, exclude: set[str] | None = None,
               kind: str | None = None) -> list[dict]:
        q = shape(binned)
        hits = []
        for it, s in zip(self.items, self.shapes):
            if exclude and it["id"] in exclude:
                continue
            if kind and it["kind"] != kind:
                continue
            hits.append((similarity(q, s), it))
        hits.sort(key=lambda h: -h[0])
        return [{**{k: v for k, v in it.items() if k != "counts"}, "cosine": round(cs, 5), "similarity": to_pct(cs)}
                for cs, it in hits[:top_k]]
