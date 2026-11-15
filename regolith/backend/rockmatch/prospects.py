"""Prospect zones: where on Mars a deposit type is *likely*, judged from orbit only.

Each zone type is a transparent rule over NASA orbital data (Mars Odyssey GRS element maps, MGS MOLA elevation),
applied to NASA's own 5 x 5 degree cells. Neighbouring qualifying cells join into one zone. Rover measurements
inside a zone are reported as ground truth, but never used to draw it."""
from __future__ import annotations

import math
import statistics

from .elements import percentile
from .predict import ground_from_grs, water_yield

TOP_PCT = 85            # "top 15 %" of each orbital map

KINDS = {
    "salt": {
        "label": "Salt basin candidates", "short": "Salt basin",
        "rule": "Odyssey GRS chlorine in the planet's top 15% and ground lower than the median (MOLA)",
        "why": "Chloride salts are left behind where salty water pools and evaporates, and water collects in low "
               "ground. So low-lying, chlorine-rich areas are the likeliest places for salt deposits like the "
               "chlorine-rich rocks Curiosity measured in Gale crater (up to 19.75 wt% Cl with sodium to match, "
               "consistent with rock salt).",
        "related": ["halide"], "grs": "Cl", "low": True, "link": "salty",
    },
    "water": {
        "label": "Water-rich ground", "short": "Water-rich ground",
        "rule": "Odyssey GRS water-equivalent hydrogen in the planet's top 15% (NASA has no data near the poles)",
        "why": "Gamma rays from hydrogen show water held in roughly the top few tens of centimetres. At these "
               "latitudes it is most likely bound in hydrated minerals such as clays and sulfates, or possibly "
               "buried ice - either way, the best places outside the poles to extract water.",
        "related": ["sulfate", "mg_sulfate", "fe_sulfate", "ca_sulfate", "al_clay"], "grs": "H2O", "low": False,
        "link": "odyssey",
    },
    "potassium": {
        "label": "Potassium-rich ground", "short": "Potassium-rich",
        "rule": "Odyssey GRS potassium in the planet's top 15%",
        "why": "Potassium concentrates in magma that partly crystallised before erupting, so these areas are "
               "candidates for alkali-rich igneous rock like the kind Curiosity found in Gale crater. Potassium can "
               "also be concentrated by sediments or weathering, so this is a lead, not a rock identification.",
        "related": ["alkali"], "grs": "K", "low": False, "link": "odyssey",
    },
}

SITE_NAMES = {"Curiosity": "Gale crater", "Spirit": "Gusev crater", "Opportunity": "Meridiani Planum"}


def _cell_of(lat: float, lon: float) -> tuple[float, float]:
    return (math.floor((lat + 90) / 5) * 5 - 90 + 2.5, math.floor((lon + 180) / 5) * 5 - 180 + 2.5)


def _zones(cells: set[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Connected groups of 5 deg cells (edge neighbours, longitude wraps around)."""
    left, out = set(cells), []
    while left:
        stack, comp = [left.pop()], []
        while stack:
            la, lo = stack.pop()
            comp.append((la, lo))
            for dla, dlo in ((5, 0), (-5, 0), (0, 5), (0, -5)):
                n = (la + dla, (lo + dlo + 180) % 360 - 180)
                if n in left:
                    left.remove(n)
                    stack.append(n)
        out.append(comp)
    return out


def _centre(comp: list[tuple[float, float]], weights: list[float]) -> tuple[float, float]:
    """Area-weighted centre; longitude averaged on the circle so zones across 180 deg stay put."""
    w = [wt * math.cos(math.radians(la)) for (la, _), wt in zip(comp, weights)]
    tot = sum(w)
    lat = sum(wi * la for wi, (la, _) in zip(w, comp)) / tot
    x = sum(wi * math.cos(math.radians(lo)) for wi, (_, lo) in zip(w, comp))
    y = sum(wi * math.sin(math.radians(lo)) for wi, (_, lo) in zip(w, comp))
    return lat, math.degrees(math.atan2(y, x))


def cell_area_km2(lat: float, r_km: float = 3389.5) -> float:
    d = math.radians(5)
    return r_km ** 2 * d * abs(math.sin(math.radians(lat + 2.5)) - math.sin(math.radians(lat - 2.5)))


def build(grs: dict, elev: dict[tuple[float, float], float], rocks: list[dict], classes: dict[str, str],
          gale_h2o: float | None = None) -> dict:
    """Prospect zones for every kind. elev: mean MOLA elevation (m) per 5 deg cell centre."""
    out = {}
    cellval = {el: {(c[0], c[1]): c[2] for c in grs[el]["cells"]} for el in ("Fe", "Si", "K", "Cl", "H2O") if el in grs}

    def zone_mean(el, comp):
        v = [cellval[el][c] for c in comp if c in cellval.get(el, {})]
        return statistics.fmean(v) if v else None
    for kind, k in KINDS.items():
        g = grs[k["grs"]]
        val = {(c[0], c[1]): c[2] for c in g["cells"]}
        thr = percentile(sorted(val.values()), TOP_PCT)
        elev_med = statistics.median(elev[c] for c in val)
        chosen = {c for c, v in val.items() if v >= thr and (not k["low"] or elev[c] < elev_med)}
        zones = []
        for comp in _zones(chosen):
            vals = [val[c] for c in comp]
            lat, lon = _centre(comp, [1.0] * len(comp))
            members = set(comp)
            ground = []
            for rover, site in SITE_NAMES.items():
                rs = [r for r in rocks if r["rover"] == rover and _cell_of(r["lat"], r["lon"]) in members]
                if rs:
                    rel = [r for r in rs if r["deposit"] in k["related"]]
                    ground.append({"rover": rover, "site": site, "n": len(rs), "n_related": len(rel),
                                   "related": sorted({classes.get(r["deposit"], r["deposit"]) for r in rel})})
            zones.append({
                "cells": [[la, lo] for la, lo in sorted(comp)], "n_cells": len(comp),
                "area_km2": round(sum(cell_area_km2(la) for la, _ in comp), -3),
                "lat": round(lat, 2), "lon": round(lon, 2),
                "mean": round(statistics.fmean(vals), 3), "max": max(vals),
                "elev_m": round(statistics.fmean(elev[c] for c in comp)), "ground": ground,
                # predictions for the zone as a whole (orbital averages -> what an APXS / a water plant would see)
                "predicted_soil": ground_from_grs({el: zone_mean(el, comp) for el in ("Fe", "Si", "K", "Cl")}),
                "water": water_yield(round(zone_mean("H2O", comp), 2), gale_h2o) if zone_mean("H2O", comp) else None,
            })
        zones.sort(key=lambda z: -z["area_km2"])
        out[kind] = {**{key: k[key] for key in ("label", "short", "rule", "why", "related", "grs", "link")},
                     "unit": g["unit"], "threshold": thr, "elev_median_m": round(elev_med) if k["low"] else None,
                     "n_cells": len(chosen), "zones": zones}
    return out
