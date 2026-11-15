"""Nearest-match search over APXS compositions.

Each element is standardised by its spread across all Mars measurements (z-scores),
so a 1 wt% change in MnO counts as much as a much larger change in SiO2 when both
are equally unusual. Trace elements (ppm) are compared on a log scale and weighted
half. Distance = weighted RMS z-difference over the elements both samples share.
"""
from __future__ import annotations

import math

from .chemistry import CLASS_BY_ID, ELEMENTS, TRACES
from .geo import distance_m

MIN_SHARED_WEIGHT = 3.0   # need at least ~3 major elements in common


def _t(el: str, v: float) -> float:
    return math.log10(max(v, 0.0) + 10.0) if el in TRACES else v


def similarity_pct(d: float) -> int:
    return int(round(100 * math.exp(-0.5 * d * d)))


class Matcher:
    def __init__(self, rocks: list[dict]):
        self.rocks = rocks
        self.stats: dict[str, tuple[float, float]] = {}
        for el in ELEMENTS:
            vals = [_t(el, r["chemistry"][el]) for r in rocks if el in r["chemistry"]]
            if len(vals) >= 2:
                m = sum(vals) / len(vals)
                sd = math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))
                self.stats[el] = (m, max(sd, 1e-6))
        self.weights = {el: (0.5 if el in TRACES else 1.0) for el in ELEMENTS}
        self.vectors = [self.features(r["chemistry"]) for r in rocks]

    def features(self, chem: dict) -> dict[str, float]:
        return {el: (_t(el, v) - self.stats[el][0]) / self.stats[el][1]
                for el, v in chem.items() if el in self.stats}

    def distance(self, fa: dict, fb: dict) -> float | None:
        num = den = 0.0
        for el, a in fa.items():
            b = fb.get(el)
            if b is None:
                continue
            w = self.weights[el]
            num += w * (a - b) ** 2
            den += w
        if den < MIN_SHARED_WEIGHT:
            return None
        return math.sqrt(num / den)

    def search(self, chem: dict, top_k: int = 5, lat: float | None = None, lon: float | None = None,
               exclude: set[str] | None = None, rover: str | None = None) -> list[dict]:
        q = self.features(chem)
        hits = []
        for rock, vec in zip(self.rocks, self.vectors):
            if exclude and rock["id"] in exclude:
                continue
            if rover and rock["rover"].lower() != rover.lower():
                continue
            d = self.distance(q, vec)
            if d is not None:
                hits.append((d, rock))
        hits.sort(key=lambda h: h[0])
        out = []
        for d, rock in hits[:top_k]:
            item = {"rock": rock, "chem_distance": round(d, 3), "similarity": similarity_pct(d)}
            if lat is not None and lon is not None and rock.get("lat") is not None:
                item["distance_m"] = round(distance_m(lat, lon, rock["lat"], rock["lon"]))
            out.append(item)
        return out

    def count_within(self, chem: dict, threshold: float, exclude: set[str] | None = None) -> int:
        q = self.features(chem)
        n = 0
        for rock, vec in zip(self.rocks, self.vectors):
            if exclude and rock["id"] in exclude:
                continue
            d = self.distance(q, vec)
            if d is not None and d <= threshold:
                n += 1
        return n


def verdict(query_class: str, matches: list[dict], n_close: int, class_count: int, total: int) -> dict:
    """Is this rock worth sampling? Combines novelty (distance) with deposit rarity."""
    cls = CLASS_BY_ID[query_class]
    rare = cls["notable"] and class_count < max(25, 0.01 * total)
    if not matches:
        return {"label": "SAMPLE", "reason": "No comparable APXS measurement exists - completely new chemistry."}
    best = matches[0]["chem_distance"]
    name = matches[0]["rock"]["name"]
    if best >= 1.25:
        return {"label": "SAMPLE", "reason": f"Chemically unlike all {total:,} measurements (closest: {name}, "
                                             f"{matches[0]['similarity']}% similar) - high science value."}
    if rare:
        return {"label": "SAMPLE", "reason": f"Rare deposit type: only {class_count} '{cls['label']}' "
                                             f"measurements exist on Mars."}
    if best < 0.35 and n_close >= 3:
        return {"label": "DUPLICATE", "reason": f"{n_close} already-measured rocks are chemically very close "
                                                f"(closest: {name}). Skip unless the geological context is new."}
    return {"label": "MAYBE", "reason": f"Similar to known rocks (closest: {name}). Sample if the geological "
                                        f"setting differs from where those were measured."}
