# Rock Match

**An APXS field guide for Mars astronauts.** An astronaut takes an APXS reading of a rock (or simulates one),
and Rock Match compares it against **all 2,475 APXS measurements** made by Curiosity, Spirit and Opportunity. It then:

- names the closest measured rocks, how similar they are, and how far away they are from you;
- classifies the deposit type (calcium-sulfate vein, opaline silica, manganese enrichment and so on);
- gives a **SAMPLE / MAYBE / DUPLICATE** verdict, weighing how new and how rare the chemistry is;
- shows the real rover close-up photos, the APXS X-ray spectrum and a chemistry chart for each rock;
- explains the likely reason for unusual chemistry, with links to the NASA/JPL pages about that rock type or region;
- maps everything on a 3D Mars globe sharpened with HiRISE imagery (0.3 m per pixel) at the rover sites;
- has **element concentration maps**: choose an element (for example chlorine) to highlight in blue where it is
  highest, from orbit (Mars Odyssey Gamma Ray Spectrometer, whole planet) and on the ground (APXS hotspots).

The APXS instrument was built by the **Canadian Space Agency**. Rock Match uses CSA Open Data directly
(the Curiosity APXS archive mirror and the instrument's lab calibration standards), alongside NASA PDS data.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend && uvicorn app:app --reload
```

Open **http://127.0.0.1:8000**. The built dataset is already in `backend/data/`, so the app works
straight after cloning.

To try it, choose a deposit type under **1 · Field reading**, press **Simulate**, then **Find match**.
Simulate fills the form with a real measurement plus its instrument error bars and places you
100–400 m from it. Rock Match should find the source rock.

### Rebuild the dataset from the original sources (optional)

```bash
python backend/scripts/fetch_data.py      # downloads ~52 MB (3,734 files) into backend/data/raw/ - resumable
python backend/scripts/build_dataset.py   # parses, places on the map, classifies -> backend/data/*.json
```

`fetch_data.py --no-spectra` skips the X-ray spectra (~5 MB instead of ~52 MB). Spectra that aren't downloaded
are fetched once on demand and cached. `fetch_data.py --only grs` downloads just the Mars Odyssey GRS element maps.

### Tests

```bash
pip install -r backend/requirements-dev.txt
cd backend && python -m pytest -q          # 53 tests: classification, matching, element maps, API, tile proxy, uploads
```

## What's in the repo

```
backend/
  app.py                    FastAPI server: API, tile proxy, serves the two web pages
  rockmatch/                chemistry rules, matching engine, element maps, "why" context, geometry, spectra, photos
  scripts/fetch_data.py     downloads every raw dataset (NASA PDS, CSA, JPL, WUSTL)
  scripts/build_dataset.py  builds the JSON datasets + prints a validation report
  data/apxs_rocks.json      2,475 measurements: chemistry ± errors, quality, location, deposit class, provenance
  data/deposits.json        259 deposit sites (same-class measurements within 250 m)
  data/traverses.json       rover paths
  data/earth_refs.json      10 CSA lab calibration standards (Earth reference rocks)
  data/grs_maps.json        Mars Odyssey GRS element maps (Cl, Fe, Si, K, Th, H2O; 5° cells)
  data/raw/                 downloaded source files (git-ignored)
  tests/                    pytest suite
frontend/                   Rock Match web app (map, deposits explorer, 3D model viewer, charts)
mars-globe/                 3D Mars globe; embedded in Rock Match and also works standalone
```

## Data sources

| Dataset | Provider | Used for | Licence |
|---|---|---|---|
| [MSL APXS RDR bundle](https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/) — concentration tables, `*rwp*.csv` oxides, `*rsp*.csv` spectra | NASA PDS Geosciences Node | Curiosity chemistry (1,768 measurements), spectra | Public domain |
| [MER APXS oxide bundle](https://pds-geosciences.wustl.edu/mer/mer1_mer2-m-apxs-5-oxide-sci-v1/) (`mer_apxs_oxide.zip`) | NASA PDS Geosciences Node | Spirit (220) and Opportunity (487) chemistry | Public domain |
| [APXS on board the Curiosity rover](https://data.asc-csa.gc.ca/en/dataset/4596426-1c8f-3l9j-895mmct858mg42) | **Canadian Space Agency Open Data** | Curiosity RDR files for sols 46–1645 (430 measurements), 10 lab calibration standards (Earth references and their spectra) | Open Government Licence – Canada |
| [Curiosity waypoints](https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json) | NASA/JPL-Caltech MMGIS | Where each Curiosity measurement was taken | NASA public data |
| [MER corrected traverses](https://an.rsl.wustl.edu/mera/AN/pages/mer/mer_traverse.htm) | PDS Analyst's Notebook (WUSTL), T. Parker | Where each Spirit and Opportunity measurement was taken | NASA PDS |
| Raw images API, PDS Imaging Node | NASA/JPL-Caltech/MSSS, NASA/JPL/Cornell/USGS | MAHLI and Microscopic Imager close-ups | NASA public data |
| Mars Trek tiles: Viking, MOLA, THEMIS, HRSC, HiRISE | NASA/JPL-Caltech, USGS, ESA/DLR/FU Berlin, ASU, UArizona | Globe imagery and elevation | NASA public data |
| [Mars Odyssey GRS element maps](https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/) (`ODY-M-GRS-5-ELEMENTS-V1.0`, smoothed 5°×5°) | NASA PDS Geosciences Node; Boynton et al. (2007), JGR 112, E12S99 | Orbital element concentration maps: Cl, Fe, Si, K, Th, water-equivalent hydrogen | Public domain |
| NASA/JPL news releases and mission pages | NASA/JPL-Caltech | "Why" links for each deposit type (for example the 2011 gypsum vein and 2022 salty-region releases) | NASA public data |
| Global CTX mosaic (via Esri) | NASA/JPL/MSSS/The Murray Lab | Globe imagery (5 m/px mosaic, streamed at up to ~10 m/px) | Free use with credit |

`backend/data/raw/MANIFEST.json` records every download (URL, licence, counts, date).

## How it works

- **Where:** each Curiosity measurement is placed at the rover's position at the start of that sol
  (JPL waypoints). Spirit and Opportunity measurements use the PDS-corrected traverses. Positions are
  typically good to within one sol's drive (~100 m). The build checks all three landing sites against their
  published coordinates (within 0.2 km).
- **Linking files:** each Curiosity table row is linked to its own `rwp`/`rsp` file by spacecraft clock and verified
  by chemistry (agreement 0.03 wt% on average, 1,760 of 1,768 linked).
- **Deposit classes:** a transparent rule set over bulk chemistry (`backend/rockmatch/chemistry.py`), for
  example Ca-sulfate veins (SO3 ≥ 18 and CaO ≥ 12 wt% at a CaSO4-like ratio) or opaline silica (SiO2 ≥ 65 wt%).
  This is a screening of chemistry, not a mineral identification. Each rock records the values that triggered
  its class.
- **Matching:** each element is standardised by its spread across all measurements. Trace metals are compared
  on a log scale. The distance is converted to a similarity percentage.
- **Element maps:** choose an element and a cut-off (top 1–50 %). Each dataset is ranked on its own:
  - **Orbit:** Odyssey GRS cells at or above that percentile are shaded blue, brighter for higher values.
    The values are NASA's own numbers; hovering shows the exact cell value and its ±1σ error.
  - **Ground:** APXS measurements at or above the APXS percentile turn blue. Those within 500 m of each other
    become a blue hotspot circle, ranked by their highest value.

  GRS reports elements (Fe, Si, K) and APXS reports oxides (FeO, SiO2, K2O). The two are never mixed, and the
  panel gives the conversion factor. Sulfur, Mg, Ca, Al, Na, P, Mn, Ti, Cr, Ni, Zn and Br have APXS data only.
  Th and hydrogen have orbital data only.
- **Why this chemistry:** for each deposit class, a short explanation of how that chemistry forms. It also lists
  which elements are far above the median, and their usual causes. Each class links to the NASA/JPL release about
  that kind of deposit. These are likely explanations from bulk chemistry, not mineral identifications.
- **Map colours:** the globe shows one colour view at a time with at most three colours, so they stay
  distinguishable, including for colour-blind viewers (checked with a palette validator).

## Known limits

- Opportunity's iron meteorites (Heat Shield Rock and others) aren't in NASA's MER oxide table, so they're not
  in the dataset. Curiosity's are.
- X-ray spectra are linked for Curiosity. MER spectra exist in PDS but aren't linked yet.
- Odyssey GRS cells are ~300 km across and see only the top few tens of centimetres. A blue cell means that
  region's average is high, not that every rock in it is. Cl, Fe, Si and hydrogen are masked poleward of ~60°
  in NASA's maps (polar frost); K and Th are global.
- Photo-based identification isn't implemented. Field photos are stored with your notes, and identification
  uses the APXS chemistry.
