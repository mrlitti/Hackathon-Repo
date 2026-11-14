"""Rock Match backend (FastAPI).

Data: 2,900+ APXS measurements from Curiosity, Spirit and Opportunity (NASA PDS + CSA),
built by scripts/build_dataset.py into data/*.json.

API
  GET  /api/health                     status + counts
  GET  /api/meta                       dataset metadata, sites, citations, deposit classes
  GET  /api/rocks                      list (filters: rover, deposit, q, quality; fields=summary|full)
  GET  /api/rocks/near                 rocks near a lat/lon
  GET  /api/rocks/{id}                 one rock + its deposit site, similar rocks, closest Earth reference
  GET  /api/rocks/{id}/spectrum        APXS X-ray spectrum (Curiosity)
  GET  /api/rocks/{id}/photos          rover close-up photos from that sol
  GET  /api/deposits                   deposit sites (clusters of same-class measurements)
  GET  /api/deposits/{id}              one deposit site with its member rocks
  GET  /api/traverses                  rover paths
  GET  /api/earth-refs                 CSA lab calibration standards (Earth reference rocks)
  GET  /api/earth-refs/{id}/spectrum   their spectra
  POST /api/classify                   deposit class for a composition
  POST /api/match                      nearest matches + sampling verdict for a composition
  POST /api/models, GET /api/models    upload / list 3D models
  POST /api/photos                     upload a rock photo

Pages: /  (Rock Match)   /globe/  (3D Mars globe, also works standalone)
Run:   cd backend && uvicorn app:app --reload
"""
from __future__ import annotations

import json
import struct
import sys
import uuid
import zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, File, HTTPException, Query, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from rockmatch.chemistry import (CLASS_BY_ID, CLASS_FAMILY, DEPOSIT_CLASSES, ELEMENTS, MAP_VIEWS,  # noqa: E402
                                 OTHER_COLOR, OXIDES, SLOT_COLORS, classify, clean_chemistry)
from rockmatch.geo import distance_m  # noqa: E402
from rockmatch.match import Matcher, similarity_pct, verdict  # noqa: E402
from rockmatch.net import http_get  # noqa: E402
from rockmatch.photos import rover_photos  # noqa: E402
from rockmatch.spectra import load_spectrum  # noqa: E402

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"
UPLOADS = BASE / "uploads"
FRONTEND = BASE.parent / "frontend"
GLOBE = BASE.parent / "mars-globe"

MODEL_EXTS = {".glb", ".gltf", ".obj", ".stl"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
SUMMARY_FIELDS = ("id", "name", "rover", "sol", "lat", "lon", "deposit", "sample_type", "deposit_site")


# --------------------------------------------------------------------------- data

def _load(name: str, default):
    p = DATA / name
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


class Store:
    def __init__(self) -> None:
        doc = _load("apxs_rocks.json", {})
        self.rocks: list[dict] = doc.get("rocks", []) if isinstance(doc, dict) else []
        self.meta: dict = doc.get("meta", {}) if isinstance(doc, dict) else {}
        self.by_id = {r["id"]: r for r in self.rocks}
        counts = Counter(r["deposit"] for r in self.rocks)
        self.classes = doc.get("classes") or [{**c, "count": counts.get(c["id"], 0), "by_rover": {}, "sites": 0}
                                              for c in DEPOSIT_CLASSES]
        self.class_counts = counts
        self.deposits: list[dict] = _load("deposits.json", {}).get("deposits", [])
        self.dep_by_id = {d["id"]: d for d in self.deposits}
        self.traverses: dict = _load("traverses.json", {})
        self.earth_refs: list[dict] = _load("earth_refs.json", {}).get("references", [])
        self.ref_by_id = {r["id"]: r for r in self.earth_refs}
        self.matcher = Matcher(self.rocks) if self.rocks else None
        # "typical Mars": the median of every APXS measurement, used to normalise chemistry charts
        self.reference = {}
        for el in ELEMENTS:
            vals = sorted(r["chemistry"][el] for r in self.rocks if el in r["chemistry"])
            if vals:
                self.reference[el] = round(vals[len(vals) // 2], 4)
        for c in self.classes:
            c["family"] = CLASS_FAMILY.get(c["id"])


store = Store()


def summary(rock: dict) -> dict:
    s = {k: rock.get(k) for k in SUMMARY_FIELDS}
    s["quality"] = rock.get("quality", {}).get("tier")
    return s


def nearest_earth_ref(chem: dict) -> dict | None:
    """Closest CSA lab standard, compared on the major oxides only (the standards' trace-element
    values are near zero, which would otherwise dominate the comparison)."""
    if not store.matcher or not store.earth_refs:
        return None
    majors = lambda c: {k: v for k, v in c.items() if k in OXIDES}  # noqa: E731
    q = store.matcher.features(majors(chem))
    best = None
    for ref in store.earth_refs:
        d = store.matcher.distance(q, store.matcher.features(majors(ref["chemistry"])))
        if d is not None and (best is None or d < best[0]):
            best = (d, ref)
    if best is None:
        return None
    d, ref = best
    return {"id": ref["id"], "name": ref["name"], "kind": ref["kind"], "similarity": similarity_pct(d),
            "chem_distance": round(d, 3), "chemistry": ref["chemistry"]}


# --------------------------------------------------------------------------- app

app = FastAPI(title="Rock Match API", version="2.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


class ChemistryIn(BaseModel):
    chemistry: dict[str, float | None] = Field(..., description="Oxides in wt%, Ni/Zn/Br in ppm")


class MatchRequest(ChemistryIn):
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-360, le=360)
    top_k: int = Field(5, ge=1, le=25)
    rover: str | None = None
    exclude_id: str | None = None


def _require_chem(raw: dict) -> dict:
    chem = clean_chemistry(raw)
    if len(chem) < 3:
        raise HTTPException(422, "Enter at least 3 elements (oxides in wt%, Ni/Zn/Br in ppm) within physical limits.")
    return chem


@app.get("/api/health")
def health():
    return {"status": "ok", "rocks_loaded": len(store.rocks), "deposit_sites": len(store.deposits),
            "earth_refs": len(store.earth_refs), "generated_utc": store.meta.get("generated_utc")}


@app.get("/api/meta")
def meta():
    return {**store.meta, "classes": store.classes, "deposit_sites": len(store.deposits),
            "earth_refs": len(store.earth_refs), "views": MAP_VIEWS, "slot_colors": SLOT_COLORS,
            "other_color": OTHER_COLOR,
            "reference": {"label": f"Median of all {len(store.rocks):,} APXS measurements",
                          "chemistry": store.reference}}


@app.get("/api/classes")
def classes():
    return {"classes": store.classes}


@app.get("/api/rocks")
def list_rocks(rover: str | None = None, deposit: str | None = None, q: str | None = None,
               quality: str | None = Query(None, pattern="^(good|fair|quick-look)$"),
               fields: str = Query("summary", pattern="^(summary|full)$"),
               limit: int = Query(5000, ge=1, le=10000), offset: int = Query(0, ge=0)):
    rocks = store.rocks
    if rover:
        wanted = {x.strip().lower() for x in rover.split(",")}
        rocks = [r for r in rocks if r["rover"].lower() in wanted]
    if deposit:
        wanted = {x.strip() for x in deposit.split(",")}
        rocks = [r for r in rocks if r["deposit"] in wanted]
    if quality:
        order = {"good": 0, "fair": 1, "quick-look": 2}
        rocks = [r for r in rocks if order[r["quality"]["tier"]] <= order[quality]]
    if q:
        ql = q.strip().lower()
        rocks = [r for r in rocks if ql in r["name"].lower() or ql in r["id"].lower()]
    page = rocks[offset:offset + limit]
    return {"total": len(rocks), "count": len(page),
            "rocks": page if fields == "full" else [summary(r) for r in page]}


@app.get("/api/rocks/near")
def rocks_near(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-360, le=360),
               radius_km: float = Query(2.0, gt=0, le=500), limit: int = Query(50, ge=1, le=500)):
    hits = []
    for r in store.rocks:
        d = distance_m(lat, lon, r["lat"], r["lon"])
        if d <= radius_km * 1000:
            hits.append({**summary(r), "distance_m": round(d)})
    hits.sort(key=lambda h: h["distance_m"])
    return {"count": len(hits[:limit]), "rocks": hits[:limit]}


def _rock(rock_id: str) -> dict:
    rock = store.by_id.get(rock_id)
    if rock is None:
        raise HTTPException(404, f"Rock '{rock_id}' not found")
    return rock


@app.get("/api/rocks/{rock_id}")
def get_rock(rock_id: str):
    rock = _rock(rock_id)
    site = store.dep_by_id.get(rock.get("deposit_site"))
    similar = store.matcher.search(rock["chemistry"], top_k=5, exclude={rock["id"]}) if store.matcher else []
    return {**rock, "class": CLASS_BY_ID[rock["deposit"]],
            "site": {k: site[k] for k in ("id", "class", "count", "lat", "lon", "radius_m", "sol_first", "sol_last")}
            if site else None,
            "similar": [{**summary(m["rock"]), "similarity": m["similarity"]} for m in similar],
            "earth_ref": nearest_earth_ref(rock["chemistry"]),
            "has_spectrum": "rsp" in rock.get("source", {})}


@app.get("/api/rocks/{rock_id}/spectrum")
def rock_spectrum(rock_id: str):
    rock = _rock(rock_id)
    rsp = rock.get("source", {}).get("rsp")
    if not rsp:
        raise HTTPException(404, "No spectrum linked for this measurement (spectra are available for Curiosity).")
    try:
        spec = load_spectrum(RAW / rsp["file"], rsp["url"], CACHE / "spectra")
    except Exception as e:  # network or file problem
        raise HTTPException(503, f"Spectrum unavailable right now: {e}") from e
    return {**spec, "source_url": rsp["url"], "source": rsp["from"]}


@app.get("/api/rocks/{rock_id}/photos")
def rock_photos(rock_id: str):
    rock = _rock(rock_id)
    try:
        return rover_photos(rock["rover"], rock["sol"], CACHE / "photos")
    except Exception as e:
        return {"rover": rock["rover"], "sol": rock["sol"], "images": [], "error": f"Photo service unavailable: {e}"}


@app.get("/api/deposits")
def list_deposits(deposit: str | None = None, rover: str | None = None, notable: bool = False,
                  min_count: int = Query(1, ge=1)):
    deps = store.deposits
    if deposit:
        wanted = {x.strip() for x in deposit.split(",")}
        deps = [d for d in deps if d["class"] in wanted]
    if rover:
        deps = [d for d in deps if d["rover"].lower() == rover.lower()]
    if notable:
        deps = [d for d in deps if CLASS_BY_ID[d["class"]]["notable"]]
    deps = [d for d in deps if d["count"] >= min_count]
    return {"count": len(deps), "deposits": deps}


@app.get("/api/deposits/{dep_id}")
def get_deposit(dep_id: str):
    d = store.dep_by_id.get(dep_id)
    if d is None:
        raise HTTPException(404, f"Deposit site '{dep_id}' not found")
    return {**d, "class_info": CLASS_BY_ID[d["class"]],
            "rocks": [summary(store.by_id[m]) for m in d["members"] if m in store.by_id]}


@app.get("/api/traverses")
def traverses():
    return store.traverses


@app.get("/api/earth-refs")
def earth_refs():
    return {"references": [{k: v for k, v in r.items() if k != "spectrum_file"} for r in store.earth_refs]}


@app.get("/api/earth-refs/{ref_id}/spectrum")
def earth_ref_spectrum(ref_id: str):
    ref = store.ref_by_id.get(ref_id)
    if ref is None or not ref.get("spectrum_file"):
        raise HTTPException(404, "No spectrum for this reference")
    return load_spectrum(RAW / ref["spectrum_file"], None, CACHE / "spectra")


@app.post("/api/classify")
def classify_endpoint(body: ChemistryIn):
    chem = _require_chem(body.chemistry)
    cid, why = classify(chem)
    return {"class": cid, "reason": why, "class_info": CLASS_BY_ID[cid], "elements_used": sorted(chem)}


@app.post("/api/match")
def match(req: MatchRequest):
    chem = _require_chem(req.chemistry)
    if not store.matcher:
        raise HTTPException(503, "No APXS data loaded - run scripts/fetch_data.py and scripts/build_dataset.py")
    cid, why = classify(chem)
    exclude = {req.exclude_id} if req.exclude_id else None
    hits = store.matcher.search(chem, top_k=req.top_k, lat=req.lat, lon=req.lon, exclude=exclude, rover=req.rover)
    n_close = store.matcher.count_within(chem, 0.6, exclude=exclude)
    result = {
        "query": {"chemistry": chem, "class": cid, "reason": why, "class_info": CLASS_BY_ID[cid],
                  "elements_used": sorted(chem)},
        "matches": [{**summary(h["rock"]), "chemistry": h["rock"]["chemistry"], "similarity": h["similarity"],
                     "chem_distance": h["chem_distance"], "distance_m": h.get("distance_m")} for h in hits],
        "verdict": verdict(cid, hits, n_close, store.class_counts.get(cid, 0), len(store.rocks)),
        "earth_ref": nearest_earth_ref(chem),
        "stats": {"total": len(store.rocks), "class_count": store.class_counts.get(cid, 0), "near_identical": n_close},
    }
    if req.lat is not None and req.lon is not None:
        same = [r for r in store.rocks if r["deposit"] == cid and r["id"] != req.exclude_id]
        if same:
            best = min(same, key=lambda r: distance_m(req.lat, req.lon, r["lat"], r["lon"]))
            result["nearest_same_class"] = {**summary(best),
                                            "distance_m": round(distance_m(req.lat, req.lon, best["lat"], best["lon"]))}
    return result


# --------------------------------------------------------------------------- tile proxy (CTX)
# The Murray Lab CTX mosaic is served by Esri. Fetching it server-side avoids intermittent browser
# CORS failures and caches tiles on disk, so repeat demos work even on weak conference Wi-Fi.
CTX_UPSTREAM = "https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile/{z}/{y}/{x}"
CTX_MAX_LEVEL = 12
def _transparent_png() -> bytes:
    """A valid 1x1 fully transparent RGBA PNG."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00")) + chunk(b"IEND", b""))


TRANSPARENT_PNG = _transparent_png()


@app.get("/api/tiles/ctx/{z}/{y}/{x}.png", include_in_schema=False)
def ctx_tile(z: int, y: int, x: int):
    if not (0 <= z <= CTX_MAX_LEVEL and 0 <= y < 2 ** z and 0 <= x < 2 ** (z + 1)):
        raise HTTPException(404, "tile out of range")
    path = CACHE / "tiles" / "ctx" / str(z) / str(y) / f"{x}.png"
    if not path.exists():
        try:
            data = http_get(CTX_UPSTREAM.format(z=z, y=y, x=x), timeout=20)
        except Exception:  # upstream hiccup: transparent tile -> globe keeps the Viking colour here
            return Response(TRANSPARENT_PNG, media_type="image/png", headers={"Cache-Control": "no-store"})
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{uuid.uuid4().hex[:6]}.part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=2592000"})


# --------------------------------------------------------------------------- uploads

def save_upload(file: UploadFile, allowed: set[str], subdir: str) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type {ext!r}. Allowed: {sorted(allowed)}")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 100 MB)")
    folder = UPLOADS / subdir
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:8]}{ext}"
    (folder / name).write_bytes(data)
    return {"name": name, "original": file.filename, "url": f"/uploads/{subdir}/{name}"}


@app.post("/api/models")
def upload_model(file: UploadFile = File(...)):
    return save_upload(file, MODEL_EXTS, "models")


@app.get("/api/models")
def list_models():
    folder = UPLOADS / "models"
    files = sorted(folder.iterdir()) if folder.exists() else []
    return {"models": [{"name": f.name, "url": f"/uploads/models/{f.name}"} for f in files if f.suffix in MODEL_EXTS]}


@app.post("/api/photos")
def upload_photo(file: UploadFile = File(...)):
    saved = save_upload(file, PHOTO_EXTS, "photos")
    saved["note"] = "Photo stored with your field notes. Identification uses APXS chemistry."
    return saved


# --------------------------------------------------------------------------- static (keep last)

UPLOADS.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")


@app.get("/globe", include_in_schema=False)
def globe_redirect():
    return RedirectResponse("/globe/")


if GLOBE.exists():
    app.mount("/globe", StaticFiles(directory=GLOBE, html=True), name="globe")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
