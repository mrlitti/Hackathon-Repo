"""Predictions one step beyond the measured values, each from well-established science, with its assumptions.

1. water_yield     - water you could extract from soil, from Odyssey GRS water-equivalent hydrogen
2. minerals        - upper-bound salt / sulfate / phosphate amounts in a reading, from mineral formulas
3. nearby          - what a rock sampled near a position is likely to be, from rover measurements around it
4. ground_from_grs - the soil composition an APXS would likely read, from Odyssey element maps

Everything here is labelled as an estimate in the app, and the error of (4) is measured at the three rover sites."""
from __future__ import annotations

import math
import statistics

from .geo import fast_distance_m

# ---------------------------------------------------------------------------- 1. water
SAM_GALE_WT = 2.0                # wt% water released by heating Gale soil to 835 C (Curiosity SAM; NASA, 2013)
SAM_LINK = {"title": "NASA: Curiosity's SAM instrument finds water and more in surface sample (2013)",
            "url": "https://www.nasa.gov/solar-system/curiositys-sam-instrument-finds-water-and-more-in-surface-sample/"}


def water_yield(h2o_wt: float, gale_h2o_wt: float | None) -> dict:
    """Litres of water per tonne of soil (1 wt% = 10 kg per tonne; 1 kg of water = 1 litre).
    Per tonne rather than per cubic metre, so no soil density has to be assumed."""
    out = {"h2o_wt": h2o_wt, "upper_l_t": round(h2o_wt * 10)}
    if gale_h2o_wt:
        share = SAM_GALE_WT / gale_h2o_wt               # fraction Curiosity actually released at Gale
        out["practical_l_t"] = round(h2o_wt * 10 * share)
        out["share"] = round(share, 2)
        out["gale_h2o_wt"] = gale_h2o_wt
    return out


# ---------------------------------------------------------------------------- 2. minerals
M = {"CaO": 56.077, "SO3": 80.063, "MgO": 40.304, "Na2O": 61.979, "Cl": 35.453, "P2O5": 141.944,
     "CaSO4": 136.14, "MgSO4": 120.37, "NaCl": 58.443, "apatite": 504.30}


def minerals(chem: dict) -> dict:
    """Upper bounds: each mineral takes as much as the limiting element allows, in a fixed order
    (phosphate, then calcium sulfate, then magnesium sulfate; chlorine to halite). APXS reports bulk oxides,
    so these are the most that could be present, not identifications."""
    mol = {k: (chem.get(k) or 0.0) / M[k] for k in ("CaO", "SO3", "MgO", "Na2O", "Cl", "P2O5")}
    out = []
    # apatite Ca5(PO4)3F: 1.5 P2O5 and 5 CaO per formula unit
    ap = min(mol["P2O5"] / 1.5, mol["CaO"] / 5)
    if ap > 0:
        mol["P2O5"] -= ap * 1.5; mol["CaO"] -= ap * 5
        out.append({"name": "Calcium phosphate", "formula": "as apatite", "wt": ap * M["apatite"],
                    "note": "apatite or merrillite; calculated as apatite"})
    cs = min(mol["CaO"], mol["SO3"])
    if cs > 0:
        mol["CaO"] -= cs; mol["SO3"] -= cs
        out.append({"name": "Calcium sulfate", "formula": "CaSO4", "wt": cs * M["CaSO4"],
                    "note": "gypsum, bassanite or anhydrite; about 26% heavier if fully hydrated as gypsum"})
    ms = min(mol["MgO"], mol["SO3"])
    if ms > 0 and mol["SO3"] > 0:
        mol["MgO"] -= ms; mol["SO3"] -= ms
        out.append({"name": "Magnesium sulfate", "formula": "MgSO4", "wt": ms * M["MgSO4"],
                    "note": "kieserite or epsomite; Mg also sits in basalt minerals, so this is the most likely to be overstated"})
    ha = min(mol["Cl"], 2 * mol["Na2O"])
    if ha > 0:
        mol["Cl"] -= ha
        out.append({"name": "Halite", "formula": "NaCl", "wt": ha * M["NaCl"],
                    "note": "rock salt; chlorine can also be in other chlorides or perchlorates"})
    out = [{**m, "wt": round(m["wt"], 1)} for m in out if m["wt"] >= 0.5]
    left = []
    if mol["SO3"] * M["SO3"] >= 1:
        left.append(f"{mol['SO3'] * M['SO3']:.1f} wt% SO3 not matched by Ca or Mg: iron sulfates, or elemental sulfur "
                    "(APXS reports all sulfur as SO3)")
    if mol["Cl"] * M["Cl"] >= 0.5:
        left.append(f"{mol['Cl'] * M['Cl']:.1f} wt% Cl beyond what sodium can hold: other chlorides or perchlorates")
    return {"minerals": out, "unassigned": left,
            "basis": "Upper bounds from the oxide amounts and each mineral's formula (normative calculation). "
                     "Only CheMin-type X-ray diffraction identifies minerals directly."}


# ---------------------------------------------------------------------------- 3. nearby
# Model chosen by a hold-out test (rockmatch/validate.py): hide each measurement and everything within 50 m of
# it, predict it from the rest. Distance-weighting with a 300 m scale and 10 prior pseudo-counts gave the best
# log loss among uniform and Gaussian weightings (150-600 m), radii of 0.5-2 km and 2-10 pseudo-counts.
NEAR_M = 1000.0
NEAR_SIGMA_M = 300.0
NEAR_ALPHA = 10.0
MIN_NEAR = 8


def class_odds(weights: dict[str, float], prior: dict[str, float]) -> dict[str, float]:
    """Probability of each deposit type from distance-weighted neighbour counts, smoothed towards the
    planet-wide mix so a handful of rocks never gives 0% or 100%."""
    tot = sum(weights.values())
    return {c: (weights.get(c, 0.0) + NEAR_ALPHA * prior.get(c, 0.0)) / (tot + NEAR_ALPHA) for c in set(weights) | set(prior)}


def near_weight(dist_m: float) -> float:
    return math.exp(-0.5 * (dist_m / NEAR_SIGMA_M) ** 2)


def nearby(lat: float, lon: float, rocks: list[dict], labels: dict[str, str], prior: dict[str, float],
           radius_m: float = NEAR_M) -> dict | None:
    """Chance that a rock sampled here is each deposit type, from rover measurements within radius_m
    (closer measurements count more)."""
    near = [(fast_distance_m(lat, lon, r["lat"], r["lon"]), r) for r in rocks]
    near = [(d, r) for d, r in near if d <= radius_m]
    if len(near) < MIN_NEAR:
        return None
    counts: dict[str, int] = {}
    weights: dict[str, float] = {}
    for d, r in near:
        counts[r["deposit"]] = counts.get(r["deposit"], 0) + 1
        weights[r["deposit"]] = weights.get(r["deposit"], 0.0) + near_weight(d)
    p = class_odds(weights, prior)
    odds = [{"class": c, "label": labels.get(c, c), "count": counts.get(c, 0), "pct": round(100 * v)} for c, v in p.items()]
    odds = [o for o in odds if o["pct"] >= 1]
    odds.sort(key=lambda o: (-o["pct"], -o["count"]))
    d, r = min(near, key=lambda x: x[0])
    return {"radius_m": radius_m, "n": len(near), "odds": odds[:6],
            "rovers": sorted({r["rover"] for _, r in near}),
            "sols": [min(x["sol"] for _, x in near), max(x["sol"] for _, x in near)],
            "nearest": {"id": r["id"], "name": r["name"], "distance_m": round(d)},
            "caveat": "Rovers chose what to measure, often the unusual rocks, so this reflects what was sampled "
                      "around here rather than a random sample of the ground."}


# ---------------------------------------------------------------------------- 4. ground from orbit
# element -> oxide mass factors (molar masses): FeO/Fe, SiO2/Si, K2O/(2 K)
GRS_TO_OXIDE = {"FeO": ("Fe", 71.844 / 55.845), "SiO2": ("Si", 60.084 / 28.086),
                "K2O": ("K", 94.196 / (2 * 39.098)), "Cl": ("Cl", 1.0)}


def ground_from_grs(values: dict[str, float]) -> dict[str, float]:
    """values: GRS element wt% for one place (keys Fe, Si, K, Cl). Returns oxide wt% as APXS would report."""
    return {ox: round(values[el] * f, 2) for ox, (el, f) in GRS_TO_OXIDE.items() if values.get(el) is not None}


def validate_ground(grs_at, rocks: list[dict]) -> dict:
    """Compare the orbital prediction with the rovers' own soil measurements at each landing area.
    grs_at(element, lat, lon) -> GRS wt% or None."""
    sites, errs = [], {ox: [] for ox in GRS_TO_OXIDE}
    for rover in ("Curiosity", "Spirit", "Opportunity"):
        rs = [r for r in rocks if r["rover"] == rover]
        soils = [r for r in rs if r.get("sample_type") == "soil"]
        if not rs or not soils:
            continue
        lat = statistics.fmean(r["lat"] for r in rs)
        lon = statistics.fmean(r["lon"] for r in rs)
        pred = ground_from_grs({el: grs_at(el, lat, lon) for el, _ in GRS_TO_OXIDE.values()})
        meas = {ox: round(statistics.median(r["chemistry"][ox] for r in soils if ox in r["chemistry"]), 2) for ox in pred}
        for ox in pred:
            errs[ox].append(abs(pred[ox] - meas[ox]) / meas[ox] * 100)
        sites.append({"rover": rover, "n_soils": len(soils), "predicted": pred, "measured": meas})
    return {"sites": sites, "error_pct": {ox: round(max(v)) for ox, v in errs.items() if v},
            "note": "Largest difference between the orbital prediction and the rover's median soil, across the three sites."}
