"""Build steps for the EVA planner terrain and the spectrum library (imported by build_dataset.py)."""
from __future__ import annotations

import json
import math
import random
import shutil
import statistics
from pathlib import Path

from rockmatch.planner import GALE_BBOX, GALE_Z, Terrain
from rockmatch.spectra import parse_spectrum
from rockmatch.spectrum_match import SpectrumLibrary, rebin, thin


def build_gale_terrain(raw: Path, out: Path, rocks: list[dict], traverse: list, report: list[str]) -> dict | None:
    """Copy the HiRISE Gale DEM tiles next to the app data and fit the grey -> metres scale against every
    Curiosity waypoint elevation (JPL), then check how much of Curiosity's real route the terrain model allows."""
    src = raw / "trek_gale_dem_z12"
    if not src.exists():
        report.append("Gale DEM: not downloaded (run fetch_data.py --only gale_dem); the EVA planner is disabled")
        return None
    dst = out / "terrain" / "gale_dem_z12"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.png"):
        if not (dst / f.name).exists() or (dst / f.name).stat().st_size != f.stat().st_size:
            shutil.copy2(f, dst / f.name)
    t = Terrain(dst, 1.0, 0.0)
    pts = [(t.grey(r["lat"], r["lon"]), r["elev_m"]) for r in rocks
           if r["rover"] == "Curiosity" and r.get("elev_m") is not None and t.covers(r["lat"], r["lon"])]
    pts = [(g, e) for g, e in pts if g is not None]
    mx, my = statistics.fmean(g for g, _ in pts), statistics.fmean(e for _, e in pts)
    scale = sum((g - mx) * (e - my) for g, e in pts) / sum((g - mx) ** 2 for g, _ in pts)
    offset = my - scale * mx
    res = [e - (scale * g + offset) for g, e in pts]
    cal = {"product": "Gale_DEM_SMG_1m (NASA Mars Trek, MRO HiRISE Gale Crater DEM)", "zoom": GALE_Z, "bbox": GALE_BBOX,
           "scale_m_per_grey": round(scale, 4), "offset_m": round(offset, 2), "n_waypoints": len(pts),
           "residual_sd_m": round(statistics.pstdev(res), 1), "median_abs_m": round(statistics.median(abs(x) for x in res), 1),
           "max_abs_m": round(max(abs(x) for x in res)), "grey_step_m": round(scale, 1)}
    # realism: slope along Curiosity's actual drive, on the same smoothed 80 m terrain the planner uses
    t = Terrain(dst, scale, offset)
    m_per_deg = 3389500 * math.pi / 180
    slopes = []

    def smooth_elev(la, lo):
        """Mean elevation over a 200 m square (5 x 5 samples): averages out the 18.6 m grey steps."""
        k = m_per_deg * math.cos(math.radians(la))
        vals = [t.elev(la + a / m_per_deg, lo + b / k) for a in (-100, -50, 0, 50, 100) for b in (-100, -50, 0, 50, 100)]
        vals = [v for v in vals if v is not None]
        return statistics.fmean(vals) if len(vals) >= 20 else None

    for la, lo, _ in traverse[::2]:
        if not t.covers(la, lo, 0.005):
            continue
        k = m_per_deg * math.cos(math.radians(la))
        e = [smooth_elev(la + a / m_per_deg, lo + b / k) for a, b in ((0, 200), (0, -200), (200, 0), (-200, 0))]
        if None in e:
            continue
        slopes.append(math.degrees(math.atan(math.hypot((e[0] - e[1]) / 400, (e[2] - e[3]) / 400))))
    if slopes:
        cal["curiosity_route"] = {"samples": len(slopes), "median_slope_deg": round(statistics.median(slopes), 1),
                                  "under_15_pct": round(100 * sum(s <= 15 for s in slopes) / len(slopes), 1),
                                  "under_20_pct": round(100 * sum(s <= 20 for s in slopes) / len(slopes), 1)}
    (out / "terrain" / "gale_dem.json").write_text(json.dumps(cal, indent=1))
    report.append(f"Gale DEM: {len(list(dst.glob('*.png')))} tiles; grey x {scale:.3f} + {offset:.0f} m fitted to "
                  f"{len(pts)} Curiosity waypoints (sd {cal['residual_sd_m']} m)"
                  + (f"; Curiosity's route under 15 deg on {cal['curiosity_route']['under_15_pct']}% of samples" if slopes else ""))
    return cal


def build_spectrum_library(raw: Path, out: Path, rocks: list[dict], refs: list[dict], report: list[str]) -> dict:
    items = []
    for r in rocks:
        rsp = r.get("source", {}).get("rsp")
        if not rsp or not (raw / rsp["file"]).exists():
            continue
        sp = parse_spectrum((raw / rsp["file"]).read_text(errors="replace"))
        items.append({"id": r["id"], "kind": "rock", "name": r["name"], "rover": r["rover"], "sol": r["sol"],
                      "deposit": r["deposit"], "live_s": sp["live_time_s"], "counts": rebin(sp["energy_kev"], sp["counts"])})
    for ref in refs:
        if not ref.get("spectrum_file") or not (raw / ref["spectrum_file"]).exists():
            continue
        sp = parse_spectrum((raw / ref["spectrum_file"]).read_text(errors="replace"))
        items.append({"id": ref["id"], "kind": "ref", "name": ref["name"], "rover": None, "sol": None,
                      "deposit": ref["deposit"], "description": ref["kind"], "live_s": sp["live_time_s"],
                      "counts": rebin(sp["energy_kev"], sp["counts"])})
    (out / "spectra_lib.json").write_text(json.dumps({"items": items}, separators=(",", ":")))
    n_rock = sum(1 for i in items if i["kind"] == "rock")
    report.append(f"Spectrum library: {n_rock} Curiosity spectra + {len(items) - n_rock} CSA lab standards")
    return {"items": items}


def spectrum_tests(lib: dict, n: int = 150, seed: int = 20261115) -> dict:
    """Hold-out tests of spectrum matching on real spectra."""
    rocks = [i for i in lib["items"] if i["kind"] == "rock"]
    library = SpectrumLibrary(lib["items"])
    rng = random.Random(seed)
    sample = rng.sample(rocks, min(n, len(rocks)))
    found = same_type = 0
    for it in sample:
        noisy = thin(it["counts"], 0.25, rng)                          # a quarter of the counting time
        hits = library.search(noisy, top_k=1, kind="rock")
        found += bool(hits) and hits[0]["id"] == it["id"]
        others = {o["id"] for o in rocks if o["sol"] == it["sol"]}      # hide the whole sol (same target)
        hits = library.search(it["counts"], top_k=1, exclude=others, kind="rock")
        same_type += bool(hits) and hits[0]["deposit"] == it["deposit"]
    return {"n": len(sample), "seed": seed, "quarter_counts_found_pct": round(100 * found / len(sample), 1),
            "other_sol_same_type_pct": round(100 * same_type / len(sample), 1)}
