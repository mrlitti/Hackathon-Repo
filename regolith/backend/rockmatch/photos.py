"""Real rover close-up photos for an APXS measurement sol.

Curiosity: MAHLI hand-lens images from NASA's raw image service.
Spirit / Opportunity: Microscopic Imager browse JPEGs from the PDS Imaging Node.
Results are cached on disk so each sol is only looked up once.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path

from .net import dir_listing, http_json

MSL_API = "https://mars.nasa.gov/api/v1/raw_image_items/"
MSL_PAGE = "https://science.nasa.gov/mission/msl-curiosity/"
MER_BROWSE = {
    "Opportunity": "https://planetarydata.jpl.nasa.gov/img/data/mer/opportunity/mer1mo_0xxx/browse",
    "Spirit": "https://planetarydata.jpl.nasa.gov/img/data/mer/spirit/mer2mo_0xxx/browse",
}
CREDITS = {"Curiosity": "NASA/JPL-Caltech/MSSS (MAHLI)", "Spirit": "NASA/JPL/Cornell/USGS (Microscopic Imager)",
           "Opportunity": "NASA/JPL/Cornell/USGS (Microscopic Imager)"}


def _msl(sol: int, limit: int) -> list[dict]:
    params = {"order": "date_taken asc", "per_page": 100, "page": 0, "condition_1": "msl:mission",
              "condition_2": f"{sol}:sol:gte", "condition_3": f"{sol}:sol:lte", "search": "MAHLI"}
    items = http_json(MSL_API + "?" + urllib.parse.urlencode(params)).get("items", [])

    def rank(it):
        ext = it.get("extended") or {}
        if "focus_merge" in (ext.get("filter_name") or ""):
            return 0
        return {"full": 1, "subframe": 2}.get(ext.get("sample_type"), 3)

    items = [it for it in items if it.get("instrument") == "MAHLI"
             and (it.get("extended") or {}).get("sample_type") != "thumbnail" and it.get("https_url")]
    items.sort(key=rank)
    return [{"url": it["https_url"], "thumb": it["https_url"], "title": it.get("title") or f"Sol {sol} MAHLI",
             "date": it.get("date_taken"), "sol": sol,
             "page": f"https://mars.nasa.gov/raw_images/{it['id']}?site=msl" if it.get("id") else None}
            for it in items[:limit]]


def _mer(rover: str, sol: int, limit: int) -> list[dict]:
    base = MER_BROWSE[rover]
    url = f"{base}/sol{sol:04d}/edr/"
    try:
        names = dir_listing(url)
    except Exception:
        return []
    jpgs = [n for n in names if n.lower().endswith(".img.jpg")]
    full = [n for n in jpgs if re.match(r"^[12]m\d{9}eff", n, re.I)] or \
           [n for n in jpgs if not re.match(r"^[12]m\d{9}eth", n, re.I)]
    return [{"url": url + n, "thumb": url + n, "title": f"Sol {sol} Microscopic Imager", "date": None, "sol": sol}
            for n in full[:limit]]


def rover_photos(rover: str, sol: int, cache_dir: Path, limit: int = 8) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{rover.lower()}_{sol:04d}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    images: list[dict] = []
    for s in (sol, sol - 1, sol + 1):           # close-ups are sometimes taken the sol before/after
        if s < 0:
            continue
        images = _msl(s, limit) if rover == "Curiosity" else _mer(rover, s, limit)
        if images:
            break
    if rover == "Curiosity":
        page = (images[0].get("page") if images else None) or MSL_PAGE
    else:
        page = f"{MER_BROWSE[rover]}/sol{sol:04d}/edr/"
    result = {"rover": rover, "sol": sol, "images": images, "credit": CREDITS[rover], "source_page": page,
              "fetched": int(time.time())}
    cache.write_text(json.dumps(result))
    return result
