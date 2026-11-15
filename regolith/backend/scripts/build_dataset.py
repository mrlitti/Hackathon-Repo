#!/usr/bin/env python3
"""Build the Regolith datasets from the raw downloads (run fetch_data.py first).

Outputs (backend/data/):
  apxs_rocks.json   every APXS measurement: chemistry, errors, quality, location, deposit class, provenance
  deposits.json     clusters of same-class measurements (deposit sites) per rover
  traverses.json    rover paths for the map
  earth_refs.json   CSA lab calibration standards (Earth reference rocks measured by the flight APXS)

Usage (from the repo root):  python backend/scripts/build_dataset.py
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import io
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from rockmatch.chemistry import DEPOSIT_CLASSES, ELEMENTS, OXIDES, TRACES, classify  # noqa: E402
from rockmatch.geo import MARS_EQ_RADIUS_M, fast_distance_m, wrap_lon  # noqa: E402
from rockmatch.elements import grs_value  # noqa: E402
from rockmatch.prospects import build as build_prospects  # noqa: E402
from rockmatch.terrain import cell_means, load_dem  # noqa: E402
from rockmatch.validate import run as run_validation  # noqa: E402
from build_tools_extra import build_gale_terrain, build_spectrum_library, spectrum_tests  # noqa: E402

RAW = BACKEND / "data" / "raw"
OUT = BACKEND / "data"

PDS_MSL_URL = "https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/mslapx_1xxx"
CSA_RDR_URL = "https://donnees-data.asc-csa.gc.ca/users/OpenData_DonneesOuvertes/pub/APXS/Data/msl-m-apxs-4_5-rdr-v1"
PDS_MER_URL = "https://pds-geosciences.wustl.edu/mer/mer1_mer2-m-apxs-5-oxide-sci-v1/merap_2xxx/data"

DEG_M = MARS_EQ_RADIUS_M * math.pi / 180.0
OPPORTUNITY_LANDING = (-1.9462, -5.5266)   # Eagle crater (JPL); MERB traverse is metres E/N of it
SPIRIT_PROJ_CENTER_LON = 175.5            # MERA traverse: equirectangular, centred 175.5E / 0N
CLUSTER_M = 250.0                         # same-class measurements closer than this form one deposit site

CITATIONS = {
    "MSL": "Gellert, R. et al., MSL APXS RDR bundle (msl-m-apxs-4_5-rdr-v1), NASA PDS Geosciences Node.",
    "MER": "Gellert, R. et al., MER APXS oxide abundances (mer1_mer2-m-apxs-5-oxide-sci-v1), NASA PDS Geosciences Node.",
    "CSA": "Canadian Space Agency, Alpha Particle X-Ray Spectrometer (APXS) Carried on Board the Curiosity Rover, "
           "CSA Open Data, Open Government Licence - Canada.",
    "JPL": "NASA/JPL-Caltech MMGIS, Curiosity waypoints (MSL_waypoints.json).",
    "WUSTL": "Parker, T. / PDS Geosciences Node, MER corrected traverses (Analyst's Notebook).",
}


def fnum(v) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def hours(hms: str) -> float | None:
    parts = str(hms).strip().split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (float(p) for p in parts)
    except ValueError:
        return None
    return round(h + m / 60 + s / 3600, 3)


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:48] or "target"


def pretty(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip()


def r6(x: float) -> float:
    return round(x, 6)


# =========================================================================== Curiosity (MSL)

CAL_TARGET_RE = re.compile(r"^cal[_ ]?target|^ct[_ ]|caltarget", re.I)


def read_msl_table(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = next((i for i, l in enumerate(lines) if l.lower().startswith("sol,target")), None)
    if start is None:
        return []
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    header = [h.strip().split(" ")[0] for h in next(reader)]   # "sh_tavg [C]" -> "sh_tavg"
    rows = []
    for vals in reader:
        if not vals or not vals[0].strip().isdigit():
            continue
        row = {h: (vals[i].strip() if i < len(vals) else "") for i, h in enumerate(header) if h}
        # EDR product names sit in a named column in some releases and an unnamed one in others
        row["products"] = " ".join(re.findall(r"AP[AB]_\d{9}[A-Z]{3}\d{4}", ",".join(vals), flags=re.I))
        if row.get("target") and not CAL_TARGET_RE.search(row["target"]):
            row["_table"] = path.name
            rows.append(row)
    return rows


def msl_sample_type(target: str) -> tuple[str, str]:
    t = target.lower()
    if re.search(r"tailing|presieve|postsieve|sieve|dump|drill_?fines|fines|portion|mini_?start|_pile", t):
        return "drill fines", "drilled powder"
    if re.search(r"soil|sand|dune|ripple|scoop|scuff|regolith|drift|trench|bedform|portage|rocknest", t):
        return "soil", "scuffed" if "scuff" in t and "unscuff" not in t else "undisturbed"
    if "drt" in t:
        return "rock", "brushed (DRT)"
    return "rock", "as found"


def msl_quality(life_h, fwhm, norm) -> str:
    if life_h is not None and life_h >= 1 and (fwhm or 999) <= 175 and (norm or 0) >= 25:
        return "good"
    if life_h is not None and life_h >= 0.25 and (fwhm or 999) <= 250 and (norm or 0) >= 10:
        return "fair"
    return "quick-look"


RDR_RE = re.compile(r"^ap[ab]_(\d{9})(rwp|rsp)(\d{4})\d*_+p(\d+)\.csv$")


def index_rdr_files() -> tuple[dict[str, dict], dict[int, list[str]]]:
    """sclk -> {'rwp': {...}, 'rsp': {...}} for every downloaded MSL RDR csv, plus sol -> [sclk]."""
    found: dict[str, dict] = defaultdict(dict)
    by_sol: dict[int, list[str]] = defaultdict(list)
    for source, base, url in (("CSA", RAW / "csa_apxs" / "rdr", CSA_RDR_URL),
                              ("PDS", RAW / "pds_msl_apxs" / "data", f"{PDS_MSL_URL}/data")):
        for p in sorted(base.glob("sol*/*.csv")):
            m = RDR_RE.match(p.name)
            if not m:
                continue
            sclk, kind, sol, ver = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            entry = {"file": str(p.relative_to(RAW)), "url": f"{url}/{p.parent.name}/{p.name}",
                     "from": source, "version": ver}
            prev = found[sclk].get(kind)
            if prev is None or ver > prev["version"]:
                found[sclk][kind] = entry
            if kind == "rwp" and sclk not in by_sol[sol]:
                by_sol[sol].append(sclk)
    return found, by_sol


LINK_ELEMENTS = ("SiO2", "FeO", "SO3", "CaO", "MgO", "Al2O3")
LINK_MAX_DIFF = 1.5   # mean |wt%| difference allowed between table row and rwp file


def best_rdr(chem: dict, candidates: list[str], rdr: dict, rwp_vals: dict) -> tuple[str | None, float | None]:
    """Pick the RDR whose rwp oxide values agree best with the table row."""
    best = (None, None)
    for sclk in candidates:
        if "rwp" not in rdr.get(sclk, {}):
            continue
        if sclk not in rwp_vals:
            rwp_vals[sclk] = read_rwp(RAW / rdr[sclk]["rwp"]["file"])
        rv = rwp_vals[sclk]
        diffs = [abs(rv[el] - chem[el]) for el in LINK_ELEMENTS if el in rv and el in chem]
        if len(diffs) >= 4:
            score = sum(diffs) / len(diffs)
            if best[1] is None or score < best[1]:
                best = (sclk, score)
    return best


def read_rwp(path: Path) -> dict:
    vals = {}
    for line in path.read_text(errors="replace").splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[0] in ELEMENTS:
            v = fnum(parts[1])
            if v is not None:
                vals[parts[0]] = v * 10000 if parts[0] in TRACES else v   # rwp traces are wt%
    return vals


def load_waypoints() -> list[dict]:
    feats = json.loads((RAW / "jpl_msl" / "MSL_waypoints.json").read_text())["features"]
    pts = []
    for f in feats:
        p = f["properties"]
        if p.get("sol") is None or p.get("lat") is None:
            continue
        pts.append({"sol": int(p["sol"]), "lat": float(p["lat"]), "lon": wrap_lon(float(p["lon"])),
                    "elev": fnum(p.get("elev_geoid")), "site": p.get("site"), "drive": p.get("drive"),
                    "km": (fnum(p.get("dist_total_m")) or 0) / 1000})
    pts.sort(key=lambda w: (w["sol"], w["site"] or 0, w["drive"] or 0))
    return pts


def build_msl(report: list[str]) -> tuple[list[dict], list[list]]:
    extras = RAW / "pds_msl_apxs" / "extras"
    # mno_recalib holds every measurement up to sol 1293 (it supersedes msl_apxs_sol_0_359_ver2_rg.csv)
    files = [extras / "msl_apxs_concentrations_mno_recalib.csv"]
    files += sorted((p for p in extras.glob("msl_apxs_concentrations_*.csv") if re.search(r"_\d+_\d+\.csv$", p.name)),
                    key=lambda p: int(re.search(r"_(\d+)_\d+\.csv$", p.name).group(1)))
    rows: dict[tuple, dict] = {}
    for f in files:
        for r in read_msl_table(f):
            rows[(int(r["sol"]), r["target"].lower(), r.get("start_time", ""))] = r   # later tables override
    report.append(f"MSL concentration tables: {len(files)} files, {len(rows)} unique measurements")

    rdr, rdr_by_sol = index_rdr_files()
    waypoints = load_waypoints()
    wp_sols = [w["sol"] for w in waypoints]

    rocks, seen_ids, link_scores, rwp_vals = [], Counter(), [], {}
    linked = linked_csa = rejected = 0
    for (sol, _, _), r in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[1].get("start_time", ""))):
        chem, errs = {}, {}
        for el in ELEMENTS:
            v, e = fnum(r.get(el)), fnum(r.get(f"{el}_err"))
            if v is not None and v >= 0:
                chem[el] = v
                if e is not None:
                    errs[el] = e
        if sum(el in chem for el in OXIDES) < 8:
            continue
        target = r["target"]
        stype, prep = msl_sample_type(target)
        life, fwhm, norm = hours(r.get("lifetime", "")), fnum(r.get("Fe_FWHM")), fnum(r.get("gnorm"))
        lmst = r.get("start_time", "").split("M")[-1] if "M" in r.get("start_time", "") else None

        # location: rover position at the start of the sol (last waypoint from an earlier sol)
        i = bisect.bisect_left(wp_sols, sol) - 1
        wp = waypoints[max(i, 0)]

        source = {"dataset": "MSL APXS RDR", "table": r["_table"], "fit": r.get("fit_type")}
        # EDR names embed their sol (APB_<sclk>ESC<sol>...); one release table lists products from other
        # sols, so only trust EDRs whose embedded sol matches this row.
        edrs = re.findall(r"AP[AB]_(\d{9})[A-Z]{3}(\d{4})", r.get("products", ""), flags=re.I)
        sclks = list(dict.fromkeys(s for s, esol in edrs if abs(int(esol) - sol) <= 2))
        source["edr"] = sclks
        # link to the per-measurement rwp/rsp files: listed EDRs first, else any RDR from that sol
        cands = [s for s in sclks if s in rdr] or rdr_by_sol.get(sol, [])
        sclk, score = best_rdr(chem, cands, rdr, rwp_vals)
        if sclk is not None and score <= LINK_MAX_DIFF:
            for kind in ("rwp", "rsp"):
                if kind in rdr[sclk]:
                    e = rdr[sclk][kind]
                    source[kind] = {"file": e["file"], "url": e["url"], "from": e["from"]}
            source["link_mean_abs_diff_wt"] = round(score, 3)
            linked += 1
            linked_csa += source["rwp"]["from"] == "CSA"
            link_scores.append(score)
        elif sclk is not None:
            rejected += 1

        cls, why = classify(chem, stype)
        base_id = f"MSL-{sol:04d}-{slug(target)}"
        seen_ids[base_id] += 1
        rid = base_id if seen_ids[base_id] == 1 else f"{base_id}-{seen_ids[base_id]}"
        rocks.append({
            "id": rid, "name": pretty(target), "target": target, "rover": "Curiosity", "mission": "MSL",
            "sol": sol, "lmst": lmst, "sample_type": stype, "preparation": prep,
            "lat": r6(wp["lat"]), "lon": r6(wp["lon"]),
            "elev_m": round(wp["elev"]) if wp["elev"] is not None else None,
            "traverse_km": round(wp["km"], 2),
            "location": {"method": "Rover position at start of sol (JPL waypoints)", "waypoint_sol": wp["sol"],
                         "site": wp["site"], "drive": wp["drive"]},
            "chemistry": {k: round(v, 4 if k not in TRACES else 0) for k, v in chem.items()},
            "errors": {k: round(v, 4 if k not in TRACES else 0) for k, v in errs.items()},
            "quality": {"tier": msl_quality(life, fwhm, norm), "lifetime_h": life, "fwhm_ev": fwhm,
                        "norm_pct": norm, "sensor_temp_c": fnum(r.get("sh_tavg"))},
            "deposit": cls, "deposit_reason": why,
            "note": (r.get("Notes") or "").strip() or None,     # e.g. "S assumed as SO3" (elemental sulfur)
            "source": source,
        })
    report.append(f"Curiosity: {len(rocks)} measurements kept; {linked} linked to rwp/rsp files "
                  f"({linked_csa} from the CSA mirror, {linked - linked_csa} from PDS); "
                  f"{rejected} candidate links rejected (chemistry disagreed by > {LINK_MAX_DIFF} wt%)")
    if link_scores:
        report.append(f"  linked rwp files agree with the tables to {sum(link_scores) / len(link_scores):.3f} wt% on average "
                      f"(worst {max(link_scores):.2f} wt%) over {', '.join(LINK_ELEMENTS)}")
    path = [[r6(w["lat"]), r6(w["lon"]), w["sol"]] for w in waypoints]
    return rocks, path


# =========================================================================== Spirit + Opportunity (MER)

MER_TYPES = {"S": "soil", "R": "rock", "C": "cobble", "O": "rock"}
MER_PREP = {"U": "undisturbed", "D": "disturbed", "T": "trench", "C": "crest", "B": "brushed (RAT)",
            "R": "abraded (RAT grind)", "F": "other", "": "as found"}


def load_mer_traverse(rover: str) -> list[dict]:
    fname = "MERA_traverse.csv" if rover == "Spirit" else "MERB_traverse_5130.csv"
    out = []
    with open(RAW / "wustl_mer_traverse" / fname, newline="") as f:
        for r in csv.DictReader(f):
            x, y = fnum(r["CORRECTED_X"]), fnum(r["CORRECTED_Y"])
            s0, s1 = int(float(r["START_SOL"])), int(float(r["END_SOL"]))
            if x is None or y is None:
                continue
            if rover == "Spirit":
                lat, lon = y / DEG_M, SPIRIT_PROJ_CENTER_LON + x / DEG_M
            else:
                lat0, lon0 = OPPORTUNITY_LANDING
                lat = lat0 + y / DEG_M
                lon = lon0 + x / (DEG_M * math.cos(math.radians(lat0)))
            out.append({"s0": s0, "s1": s1, "lat": lat, "lon": wrap_lon(lon)})
    return out


def mer_position(trav: list[dict], sol: int) -> dict:
    for p in trav:                       # first position held during the sol (= before that sol's drive)
        if p["s0"] <= sol <= p["s1"]:
            return p
    before = [p for p in trav if p["s1"] < sol]
    return before[-1] if before else trav[0]


def build_mer(report: list[str]) -> tuple[list[dict], dict]:
    rocks, paths = [], {}
    for fname, rover, mission, letter in (("apxs_oxides_mer2.csv", "Spirit", "MER-A", "A"),
                                          ("apxs_oxides_mer1.csv", "Opportunity", "MER-B", "B")):
        trav = load_mer_traverse(rover)
        seen = Counter()
        n0 = len(rocks)
        with open(RAW / "pds_mer_apxs" / fname, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                spec = (r.get("Spectrum") or "").strip()
                m = re.match(rf"{letter}(\d+)", spec)
                if not m:
                    continue
                sol = int(m.group(1))
                chem, errs = {}, {}
                for el in ELEMENTS:
                    v, e = fnum(r.get(el)), fnum(r.get(f"{el}.err"))
                    if v is not None and v >= 0:
                        chem[el] = v
                        if e is not None:
                            errs[el] = e
                if sum(el in chem for el in OXIDES) < 8:
                    continue
                code = (r.get("Type") or "").strip().upper()
                stype = MER_TYPES.get(code[:1], "rock")
                prep = MER_PREP.get(code[1:2], "as found")
                name = (r.get("Name") or spec).strip()
                pos = mer_position(trav, sol)
                hrs, norm = fnum(r.get("Time/h")), fnum(r.get("Norm"))
                tier = "good" if (hrs or 0) >= 1 and (norm or 0) >= 25 else "fair" if (hrs or 0) >= 0.25 else "quick-look"
                cls, why = classify(chem, stype)
                base = f"{mission}-{sol:04d}-{slug(name)}"
                seen[base] += 1
                rid = base if seen[base] == 1 else f"{base}-{seen[base]}"
                rocks.append({
                    "id": rid, "name": pretty(name), "target": name, "rover": rover, "mission": mission,
                    "sol": sol, "lmst": None, "sample_type": stype, "preparation": prep,
                    "lat": r6(pos["lat"]), "lon": r6(pos["lon"]), "elev_m": None, "traverse_km": None,
                    "location": {"method": "PDS Analyst's Notebook corrected traverse", "type_code": code},
                    "chemistry": {k: round(v, 4 if k not in TRACES else 0) for k, v in chem.items()},
                    "errors": {k: round(v, 4 if k not in TRACES else 0) for k, v in errs.items()},
                    "quality": {"tier": tier, "lifetime_h": hrs, "fwhm_ev": None, "norm_pct": norm, "sensor_temp_c": None},
                    "deposit": cls, "deposit_reason": why,
                    "source": {"dataset": "MER APXS oxide abundances", "table": fname, "spectrum_id": spec,
                               "url": f"{PDS_MER_URL}/{fname}"},
                })
        report.append(f"{rover}: {len(rocks) - n0} measurements")
        pts, last = [], None
        for p in trav:
            key = (round(p["lat"], 6), round(p["lon"], 6))
            if key != last:
                pts.append([r6(p["lat"]), r6(p["lon"]), p["s0"]])
                last = key
        step = max(1, len(pts) // 4000)
        paths[rover] = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
    return rocks, paths


# =========================================================================== Earth references (CSA)

EARTH_NAMES = {
    "agv2": ("AGV-2", "Andesite (USGS reference rock, Guano Valley, Oregon)"),
    "ali": ("AL-I", "Albite feldspar (ANRT reference mineral)"),
    "bcr2": ("BCR-2", "Basalt (USGS reference rock, Columbia River, Oregon)"),
    "ben": ("BE-N", "Basalt (ANRT reference rock, France)"),
    "bt2_cal": ("BT-2", "APXS calibration target (pre-flight lab measurement)"),
    "gh": ("GH", "Granite (ANRT reference rock, France)"),
    "gsn": ("GS-N", "Granite (ANRT reference rock, France)"),
    "mica_mg": ("Mica-Mg", "Phlogopite mica (ANRT reference mineral)"),
    "pms": ("PM-S", "Laboratory reference rock"),
    "sio2": ("SiO2", "Pure silica powder"),
}


def build_earth_refs(report: list[str]) -> list[dict]:
    refs = []
    for p in sorted((RAW / "csa_apxs" / "calibration").glob("apxs_pfm2008_concentrations_*.csv")):
        code = p.stem.replace("apxs_pfm2008_concentrations_", "")
        lines = p.read_text(errors="replace").splitlines()
        desc = lines[0].strip().strip('"') if lines else ""
        chem, errs = {}, {}
        for line in lines[2:]:
            parts = [x.strip().strip('"') for x in line.split(",")]
            if len(parts) < 2:
                continue
            el, v, e = parts[0], fnum(parts[1]), fnum(parts[2]) if len(parts) > 2 else None
            if v is None:
                continue
            if el in ("Fe2O3T", "Fe2O3"):            # total iron as Fe2O3 -> FeO
                el, v, e = "FeO", v * 0.8998, (e * 0.8998 if e is not None else None)
            if el in TRACES:                          # calibration traces are in wt%
                v, e = v * 10000, (e * 10000 if e is not None else None)
            if el in ELEMENTS:
                chem[el] = round(v, 4)
                if e is not None:
                    errs[el] = round(e, 4)
        if sum(el in chem for el in OXIDES) < 6:
            continue
        short, kind = EARTH_NAMES.get(code, (code.upper(), "Laboratory reference sample"))
        spec = p.with_name(p.name.replace("concentrations", "spectrum"))
        if not spec.exists() and code == "bt2_cal":
            spec = p.with_name("apxs_pfm2008_spectrum_bt2_caltarg.csv")
        cls, why = classify(chem, "rock")
        refs.append({"id": f"CSA-{code}", "code": code, "name": short, "kind": kind, "description": desc,
                     "chemistry": chem, "errors": errs, "deposit": cls, "deposit_reason": why,
                     "spectrum_file": str(spec.relative_to(RAW)) if spec.exists() else None,
                     "source": CITATIONS["CSA"]})
    report.append(f"CSA calibration standards (Earth references): {len(refs)}")
    return refs


# =========================================================================== orbital element maps (Odyssey GRS)

GRS_ELEMENTS = {"Cl": ("cl", "Chlorine"), "Fe": ("fe", "Iron"), "Si": ("si", "Silicon"), "K": ("k", "Potassium"),
                "Th": ("th", "Thorium"), "H2O": ("h2o", "Water-equivalent hydrogen")}
GRS_UNITS = {"WEIGHT PERCENT": "wt%", "PARTS PER MILLION": "ppm"}


def build_grs(report: list[str]) -> dict:
    d = RAW / "pds_ody_grs"
    out = {}
    if not d.exists():
        report.append("Odyssey GRS maps: not downloaded (run fetch_data.py --only grs)")
        return out
    for key, (code, label) in GRS_ELEMENTS.items():
        lbl = (d / f"{code}_sr_5x5.lbl").read_text(errors="replace")
        units = re.findall(r'UNIT\s*=\s*"([^"]+)"', lbl)
        unit = GRS_UNITS.get(units[2] if len(units) > 2 else "", "wt%")      # column 3 = concentration
        cells = []
        for line in (d / f"{code}_sr_5x5.tab").read_text().splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            # columns (PDS label): centre lat, centre lon (0-360, east-positive - verified against NASA's browse
            # maps), concentration, SIGMA, SIGMA WITH CFS (also includes the correction-factor errors)
            lat, lon, conc, sig, sig_cfs = (float(x) for x in parts[:5])
            if conc >= 9999 or lon > 360:
                continue
            # SIGMA WITH CFS is "N/A" where no correction factors apply (all of K and Th): SIGMA is then the full error
            err = sig_cfs if sig_cfs < 9999 else sig if sig < 9999 else None
            cells.append([lat, wrap_lon(lon), conc, err])
        vals = sorted(c[2] for c in cells)
        # NASA's polar mask follows a wavy edge: report where data stops (cell edges), across longitudes
        north, south = defaultdict(lambda: -90.0), defaultdict(lambda: 90.0)
        for la, lo, *_ in cells:
            north[lo] = max(north[lo], la + 2.5)
            south[lo] = min(south[lo], la - 2.5)
        out[key] = {"label": label, "unit": unit, "file": f"{code}_sr_5x5.tab", "cells": cells,
                    "min": vals[0], "max": vals[-1], "median": statistics.median(vals),
                    "lat_range": [min(c[0] for c in cells), max(c[0] for c in cells)],
                    "data_edge": {"north": [min(north.values()), max(north.values())],
                                  "south": [max(south.values()), min(south.values())]}}
        report.append(f"Odyssey GRS {label}: {len(cells)} cells, {vals[0]:.3f}-{vals[-1]:.3f} {unit}")
    return out


# =========================================================================== deposits

def cluster_deposits(rocks: list[dict]) -> list[dict]:
    """Single-linkage clusters of same-class measurements within CLUSTER_M of each other."""
    groups = defaultdict(list)
    for r in rocks:
        groups[(r["rover"], r["deposit"])].append(r)
    cell_deg = CLUSTER_M / DEG_M
    deposits = []
    for (rover, cls), members in groups.items():
        parent = list(range(len(members)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        grid = defaultdict(list)
        for i, r in enumerate(members):
            grid[(int(r["lat"] // cell_deg), int(r["lon"] // cell_deg))].append(i)
        for (cy, cx), idxs in grid.items():
            near = [j for dy in (-1, 0, 1) for dx in (-1, 0, 1) for j in grid.get((cy + dy, cx + dx), [])]
            for i in idxs:
                for j in near:
                    if j > i and fast_distance_m(members[i]["lat"], members[i]["lon"],
                                                 members[j]["lat"], members[j]["lon"]) <= CLUSTER_M:
                        parent[find(i)] = find(j)
        clusters = defaultdict(list)
        for i in range(len(members)):
            clusters[find(i)].append(members[i])
        for ms in clusters.values():
            lat = sum(m["lat"] for m in ms) / len(ms)
            lon = sum(m["lon"] for m in ms) / len(ms)
            mean = {el: round(sum(m["chemistry"][el] for m in ms if el in m["chemistry"]) /
                              max(1, sum(el in m["chemistry"] for m in ms)), 3) for el in ELEMENTS}
            names = list(dict.fromkeys(m["name"] for m in ms))
            deposits.append({
                "class": cls, "rover": rover, "count": len(ms), "lat": r6(lat), "lon": r6(lon),
                "radius_m": round(max(fast_distance_m(lat, lon, m["lat"], m["lon"]) for m in ms)),
                "sol_first": min(m["sol"] for m in ms), "sol_last": max(m["sol"] for m in ms),
                "names": names[:8], "members": [m["id"] for m in sorted(ms, key=lambda m: m["sol"])],
                "mean_chemistry": mean,
            })
    order = {c["id"]: i for i, c in enumerate(DEPOSIT_CLASSES)}
    deposits.sort(key=lambda d: (order[d["class"]], -d["count"], d["sol_first"]))
    counters = Counter()
    for d in deposits:
        counters[d["class"]] += 1
        d["id"] = f"{d['class']}-{counters[d['class']]:03d}"
    rock_dep = {mid: d["id"] for d in deposits for mid in d["members"]}
    for r in rocks:
        r["deposit_site"] = rock_dep.get(r["id"])
    return deposits


# =========================================================================== main

def main() -> None:
    if not (RAW / "pds_msl_apxs").exists():
        sys.exit("Raw data not found - run: python backend/scripts/fetch_data.py")
    report: list[str] = []
    msl, msl_path = build_msl(report)
    mer, mer_paths = build_mer(report)
    rocks = msl + mer
    refs = build_earth_refs(report)
    grs = build_grs(report)
    prospects = None
    if grs and (RAW / "trek_mola_dem_z2").exists():
        elev = cell_means(load_dem(RAW / "trek_mola_dem_z2"))
        cur = [r for r in rocks if r["rover"] == "Curiosity"]
        gale_h2o = grs_value(grs, "H2O", sum(r["lat"] for r in cur) / len(cur), sum(r["lon"] for r in cur) / len(cur))
        prospects = build_prospects(grs, elev, rocks, {c["id"]: c["label"] for c in DEPOSIT_CLASSES}, gale_h2o)
        for k, v in prospects.items():
            report.append(f"Prospect zones - {v['label']}: {v['n_cells']} cells in {len(v['zones'])} zones")
    else:
        report.append("Prospect zones: skipped (needs fetch_data.py --only grs and --only mola)")
    deposits = cluster_deposits(rocks)

    cls_counts = Counter(r["deposit"] for r in rocks)
    by_rover = defaultdict(Counter)
    for r in rocks:
        by_rover[r["deposit"]][r["rover"]] += 1
    classes = [{**c, "count": cls_counts.get(c["id"], 0), "by_rover": dict(by_rover[c["id"]]),
                "sites": sum(1 for d in deposits if d["class"] == c["id"])} for c in DEPOSIT_CLASSES]

    sites = {}
    for rover in ("Curiosity", "Spirit", "Opportunity"):
        rs = [r for r in rocks if r["rover"] == rover]
        lats, lons = [r["lat"] for r in rs], [r["lon"] for r in rs]
        sites[rover] = {"count": len(rs), "sol_first": min(r["sol"] for r in rs), "sol_last": max(r["sol"] for r in rs),
                        "lat": r6(sum(lats) / len(lats)), "lon": r6(sum(lons) / len(lons)),
                        "bbox": [min(lons), min(lats), max(lons), max(lats)]}

    manifest = json.loads((RAW / "MANIFEST.json").read_text()) if (RAW / "MANIFEST.json").exists() else {}
    meta = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "count": len(rocks), "sites": sites, "elements": ELEMENTS,
        "units": {**{e: "wt%" for e in OXIDES}, **{e: "ppm" for e in TRACES}},
        "citations": CITATIONS, "raw_retrieved_utc": manifest.get("_retrieved_utc"),
        "classification_note": "Deposit classes are a rule-based screening of bulk APXS chemistry, "
                               "not a mineral identification.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "apxs_rocks.json").write_text(json.dumps({"meta": meta, "classes": classes, "rocks": rocks},
                                                    separators=(",", ":")))
    (OUT / "deposits.json").write_text(json.dumps({"cluster_m": CLUSTER_M, "deposits": deposits}, separators=(",", ":")))
    (OUT / "traverses.json").write_text(json.dumps({"Curiosity": msl_path, **mer_paths}, separators=(",", ":")))
    (OUT / "earth_refs.json").write_text(json.dumps({"source": CITATIONS["CSA"], "references": refs}, indent=1))
    (OUT / "grs_maps.json").write_text(json.dumps({
        "source": "Mars Odyssey Gamma Ray Spectrometer element concentration maps (ODY-M-GRS-5-ELEMENTS-V1.0, "
                  "NASA PDS Geosciences Node), collected 2002-06-04 to 2005-04-03. Smoothed from 2x2 degree data with "
                  "a 10-degree boxcar and rebinned on a 5x5 degree grid. Boynton et al. (2007), JGR 112, E12S99.",
        "url": "https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/",
        "browse": "https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx/browse/",
        "note": "NASA masks all non-radioactive elements in the polar regions, where it cannot yet correct for "
                "dilution by water ice; K and Th are global. Gamma rays come from roughly the top few tens of "
                "centimetres of the surface (Boynton et al. 2007). Errors are 1 sigma: NASA's SIGMA WITH CFS (which "
                "includes correction-factor errors) or SIGMA where no correction factors apply (K, Th).",
        "maps": grs}, separators=(",", ":")))
    gale = build_gale_terrain(RAW, OUT, rocks, msl_path, report)
    spec_lib = build_spectrum_library(RAW, OUT, rocks, refs, report)
    validation = run_validation(rocks)
    validation["spectra"] = spectrum_tests(spec_lib)
    if gale:
        validation["terrain"] = gale
    s_ = validation["spectra"]
    report.append(f"Spectrum hold-out: quarter-count re-measurement found {s_['quarter_counts_found_pct']}%, "
                  f"other-sol nearest spectrum same type {s_['other_sol_same_type_pct']}% ({s_['n']} spectra)")
    (OUT / "validation.json").write_text(json.dumps(validation, indent=1))
    m, nb = validation["matching"], validation["nearby"]
    report.append(f"Hold-out tests: re-measured rock found first {m['remeasure_top1_pct']}% (top five {m['remeasure_top5_pct']}%), "
                  f"same type {m['remeasure_same_type_pct']}%; new-stop forecast top-1 {nb['top1_pct']}% vs baseline "
                  f"{nb['baseline_pct']}%, top-3 {nb['top3_pct']}% over {nb['n']} cases")
    if prospects:
        (OUT / "prospects.json").write_text(json.dumps({
            "source": "Rules over NASA orbital data only: Mars Odyssey GRS element maps (ODY-M-GRS-5-ELEMENTS-V1.0) "
                      "and MGS MOLA elevation (NASA Mars Trek, Mars_MGS_MOLA_DEM_mosaic_global_463m_8), on NASA's "
                      "5x5 degree cells. Rover measurements are shown as ground truth but never used to draw zones.",
            "kinds": prospects}, separators=(",", ":")))

    print("\n".join(report))
    print(f"\nTotal: {len(rocks)} measurements, {len(deposits)} deposit sites")
    for c in classes:
        print(f"  {c['label']:<26} {c['count']:>5}  sites {c['sites']:>4}  {c['by_rover']}")
    tiers = Counter(r["quality"]["tier"] for r in rocks)
    print(f"Quality: {dict(tiers)}")

    print("\nSanity checks - well-known targets:")
    for key in ("Homestake", "Kenosha", "Fuzzy", "Wishstone", "Comanche", "Jake_Matijevic", "Buckskin",
                "Paso_Robles", "Adirondack", "Esperance", "Cururu", "Windjana"):
        for r in [r for r in rocks if key.lower() in r["target"].lower()][:1]:
            print(f"  {r['rover']:<11} sol {r['sol']:>4}  {r['name'][:28]:<28} -> {r['deposit']:<15} ({r['deposit_reason']})")
    print("Sanity checks - positions vs. known landmarks:")
    for rover, sol, label, lat, lon in (("Opportunity", 1300, "Victoria crater", -2.05, -5.50),
                                        ("Opportunity", 20, "Eagle crater landing site", -1.9462, -5.5266),
                                        ("Spirit", 18, "Columbia Memorial Station landing site", -14.5684, 175.4726),
                                        ("Curiosity", 46, "Bradbury Landing", -4.5895, 137.4417)):
        rs = sorted((r for r in rocks if r["rover"] == rover), key=lambda r: abs(r["sol"] - sol))
        if rs:
            r = rs[0]
            print(f"  {rover:<11} sol {r['sol']:>4} at {r['lat']:.4f},{r['lon']:.4f}  ~{label} ({lat},{lon}): "
                  f"{fast_distance_m(r['lat'], r['lon'], lat, lon) / 1000:.1f} km apart")
    for f in ("apxs_rocks.json", "deposits.json", "traverses.json", "earth_refs.json", "grs_maps.json", "prospects.json", "validation.json", "spectra_lib.json"):
        print(f"wrote {OUT / f} ({(OUT / f).stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
