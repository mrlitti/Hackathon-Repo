# Rock Match

Field guide for Mars astronauts: match a rock against every APXS measurement (CSA instrument) made by Curiosity, Spirit and Opportunity.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app:app --reload
```

Open http://127.0.0.1:8000

## Structure

```
backend/app.py               FastAPI server + API
backend/data/apxs_rocks.json APXS data (empty - fill from NASA PDS)
backend/uploads/             uploaded 3D models + photos
frontend/                    black UI: 3D viewer, map, input, results, detail
```

## Features (status)

| Feature | Status |
|---|---|
| 3D model viewer (.glb .gltf .obj .stl, upload or drag-drop) | working |
| Chemistry nearest-match search + distance from astronaut | working (needs data) |
| Sample / maybe / duplicate verdict | working, thresholds TODO |
| Rock detail (photo, chemistry, notes) | working (needs data) |
| Photo upload | stored; image matching TODO |
| Map of APXS sites | TODO |

## Data TODO

APXS oxide data: NASA PDS Geosciences Node (MSL, MER APXS derived-oxide products).
Convert to the schema in `backend/data/apxs_rocks.json`.
