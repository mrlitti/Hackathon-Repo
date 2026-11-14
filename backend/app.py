"""Rock Match backend (FastAPI).

Serves the frontend and a small JSON API:
  GET  /api/health          - server status + how many APXS rocks are loaded
  GET  /api/rocks           - all APXS rock measurements (optionally filter by rover)
  GET  /api/rocks/{rock_id} - one rock
  POST /api/match           - nearest-match search: chemistry (+ optional position) -> best matches
  POST /api/models          - upload a 3D model (.glb .gltf .obj .stl)
  GET  /api/models          - list uploaded 3D models
  POST /api/photos          - upload a rock photo (image matching is a TODO)

Run:  uvicorn app:app --reload   (from the backend/ folder)
"""

from __future__ import annotations

import json
import math
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data" / "apxs_rocks.json"
UPLOADS = BASE / "uploads"
FRONTEND = BASE.parent / "frontend"

MODEL_EXTS = {".glb", ".gltf", ".obj", ".stl"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

# Oxides/elements used for matching (APXS reports these as weight %).
ELEMENTS = ["Na2O", "MgO", "Al2O3", "SiO2", "P2O5", "SO3", "Cl", "K2O", "CaO", "TiO2", "Cr2O3", "MnO", "FeO"]

app = FastAPI(title="Rock Match API")


def load_rocks() -> list[dict]:
    """Load APXS measurements. Fill data/apxs_rocks.json from NASA PDS (see README)."""
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text()).get("rocks", [])


ROCKS = load_rocks()


# ---------- models ----------

class MatchRequest(BaseModel):
    chemistry: dict[str, float]          # e.g. {"SiO2": 45.1, "FeO": 19.2, ...}
    lat: float | None = None             # astronaut position (optional)
    lon: float | None = None
    top_k: int = 5


# ---------- helpers ----------

def distance_m(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance on Mars (radius 3389.5 km)."""
    r = 3_389_500
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def element_spread() -> dict[str, float]:
    """Std dev of each element across the dataset, so big oxides (SiO2) don't dominate."""
    spread = {}
    for el in ELEMENTS:
        vals = [r["chemistry"][el] for r in ROCKS if el in r.get("chemistry", {})]
        if len(vals) > 1:
            mean = sum(vals) / len(vals)
            spread[el] = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) or 1.0
    return spread


def chem_distance(a: dict, b: dict, spread: dict) -> float | None:
    shared = [el for el in ELEMENTS if el in a and el in b and el in spread]
    if not shared:
        return None
    return math.sqrt(sum(((a[el] - b[el]) / spread[el]) ** 2 for el in shared) / len(shared))


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


# ---------- routes ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "rocks_loaded": len(ROCKS)}


@app.get("/api/rocks")
def list_rocks(rover: str | None = None):
    rocks = ROCKS if not rover else [r for r in ROCKS if r.get("rover", "").lower() == rover.lower()]
    return {"count": len(rocks), "rocks": rocks}


@app.get("/api/rocks/{rock_id}")
def get_rock(rock_id: str):
    for r in ROCKS:
        if r.get("id") == rock_id:
            return r
    raise HTTPException(404, "Rock not found")


@app.post("/api/match")
def match(req: MatchRequest):
    if not ROCKS:
        return {"matches": [], "verdict": None, "note": "No APXS data loaded yet. Fill backend/data/apxs_rocks.json."}

    spread = element_spread()
    results = []
    for r in ROCKS:
        d = chem_distance(req.chemistry, r.get("chemistry", {}), spread)
        if d is None:
            continue
        item = {"rock": r, "chem_distance": round(d, 3)}
        if req.lat is not None and req.lon is not None and "lat" in r and "lon" in r:
            item["distance_m"] = round(distance_m(req.lat, req.lon, r["lat"], r["lon"]))
        results.append(item)

    results.sort(key=lambda x: x["chem_distance"])
    top = results[: req.top_k]

    # Sampling verdict. TODO: tune these thresholds with the team using real data.
    verdict = None
    if top:
        best = top[0]["chem_distance"]
        if best < 0.5:
            verdict = {"label": "DUPLICATE", "reason": "Very close to an already-measured rock."}
        elif best < 1.5:
            verdict = {"label": "MAYBE", "reason": "Similar to known rocks; sample if context is new."}
        else:
            verdict = {"label": "SAMPLE", "reason": "Unlike anything measured so far - high science value."}

    return {"matches": top, "verdict": verdict}


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
    saved["note"] = "Photo stored. Image-based matching not implemented yet."
    return saved


# ---------- static files (keep last) ----------

app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
