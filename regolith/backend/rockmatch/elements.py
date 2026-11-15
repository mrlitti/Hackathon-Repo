"""Element concentration maps: Mars Odyssey GRS (orbital, global) and APXS (rover, local).

Each source is reported in its own units and thresholds are percentiles *within* that source,
so orbital and rover values are never mixed on one scale."""
from __future__ import annotations

from .geo import fast_distance_m

# key -> label, APXS field (oxide or element), GRS map key
CATALOG = {
    "Cl": ("Chlorine", "Cl", "Cl"), "Fe": ("Iron", "FeO", "Fe"), "Si": ("Silicon", "SiO2", "Si"),
    "K": ("Potassium", "K2O", "K"), "Th": ("Thorium", None, "Th"), "H2O": ("Water-equivalent hydrogen", None, "H2O"),
    "S": ("Sulfur", "SO3", None), "Mg": ("Magnesium", "MgO", None), "Ca": ("Calcium", "CaO", None),
    "Al": ("Aluminium", "Al2O3", None), "Na": ("Sodium", "Na2O", None), "P": ("Phosphorus", "P2O5", None),
    "Mn": ("Manganese", "MnO", None), "Ti": ("Titanium", "TiO2", None), "Cr": ("Chromium", "Cr2O3", None),
    "Ni": ("Nickel", "Ni", None), "Zn": ("Zinc", "Zn", None), "Br": ("Bromine", "Br", None),
}
HOTSPOT_M = 500.0


def percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile of an ascending list."""
    k = max(0, min(len(sorted_vals) - 1, int(round(pct / 100 * len(sorted_vals) + 0.5)) - 1))
    return sorted_vals[k]


def catalog(rocks: list[dict], grs: dict) -> list[dict]:
    out = []
    for key, (label, field, gkey) in CATALOG.items():
        n = sum(1 for r in rocks if field and field in r["chemistry"])
        out.append({"key": key, "label": label, "apxs_field": field if n else None, "apxs_count": n,
                    "apxs_unit": ("ppm" if field in ("Ni", "Zn", "Br") else "wt%") if field else None,
                    "grs": bool(gkey and gkey in grs), "grs_unit": grs[gkey]["unit"] if gkey in grs else None})
    return out


def element_map(key: str, pct: float, rocks: list[dict], grs: dict, grs_meta: dict) -> dict:
    label, field, gkey = CATALOG[key]
    out = {"key": key, "label": label, "percentile": pct, "grs": None, "apxs": None}

    if gkey and gkey in grs:
        g = grs[gkey]
        vals = sorted(c[2] for c in g["cells"])
        thr = percentile(vals, pct)
        out["grs"] = {"unit": g["unit"], "threshold": thr, "min": vals[0], "max": vals[-1], "median": g["median"],
                      "cells": g["cells"], "n_high": sum(1 for v in vals if v >= thr), "n": len(vals),
                      "cell_deg": 5, "lat_range": g["lat_range"], "source": grs_meta.get("source"),
                      "url": grs_meta.get("url"), "note": grs_meta.get("note")}

    if field:
        have = [r for r in rocks if field in r["chemistry"]]
        if have:
            vals = sorted(r["chemistry"][field] for r in have)
            thr = percentile(vals, pct)
            high = [r for r in have if r["chemistry"][field] >= thr]
            # compact hotspots: seed at the highest unassigned rock, take every high rock within HOTSPOT_M of it
            # (no chaining, so a long traverse never merges into one giant region)
            spots, left = [], sorted(high, key=lambda r: -r["chemistry"][field])
            while left:
                seed = left[0]
                ms = [r for r in left if fast_distance_m(seed["lat"], seed["lon"], r["lat"], r["lon"]) <= HOTSPOT_M]
                taken = {m["id"] for m in ms}
                left = [r for r in left if r["id"] not in taken]
                lat = sum(m["lat"] for m in ms) / len(ms)
                lon = sum(m["lon"] for m in ms) / len(ms)
                top = max(ms, key=lambda m: m["chemistry"][field])
                spots.append({"lat": round(lat, 6), "lon": round(lon, 6), "count": len(ms), "rover": top["rover"],
                              "radius_m": round(max(fast_distance_m(lat, lon, m["lat"], m["lon"]) for m in ms)),
                              "max": top["chemistry"][field], "top_id": top["id"], "top_name": top["name"],
                              "ids": [m["id"] for m in ms]})
            spots.sort(key=lambda s: (-s["max"], -s["count"]))
            out["apxs"] = {"field": field, "unit": "ppm" if field in ("Ni", "Zn", "Br") else "wt%",
                           "threshold": thr, "min": vals[0], "max": vals[-1], "median": vals[len(vals) // 2],
                           "n": len(vals), "n_high": len(high), "hotspot_m": HOTSPOT_M,
                           "values": [[r["id"], r["chemistry"][field]] for r in have], "hotspots": spots}
    return out
