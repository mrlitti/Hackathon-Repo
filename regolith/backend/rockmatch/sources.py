"""Every data source Regolith uses, for the in-app "Data & methods" tab and the README.

Only NASA and Canadian Space Agency (CSA) data are used. `kind` separates the datasets the results are computed
from ("dataset"), live imagery ("imagery") and published NASA results used as constants or links ("reference")."""
from __future__ import annotations

SOURCES = [
    {"id": "msl_apxs", "agency": "NASA", "kind": "dataset",
     "name": "MSL (Curiosity) APXS RDR bundle",
     "product": "msl-m-apxs-4_5-rdr-v1: concentration tables, *rwp*.csv oxides, *rsp*.csv X-ray spectra",
     "provider": "NASA PDS Geosciences Node (instrument team: R. Gellert et al.)",
     "url": "https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/",
     "used_for": "Curiosity rock and soil chemistry with error bars, and the X-ray spectra in the Spectrum lab",
     "licence": "Public domain"},
    {"id": "mer_apxs", "agency": "NASA", "kind": "dataset",
     "name": "MER (Spirit and Opportunity) APXS oxide abundances",
     "product": "mer1_mer2-m-apxs-5-oxide-sci-v1 (mer_apxs_oxide.zip)",
     "provider": "NASA PDS Geosciences Node (instrument team: R. Gellert et al.)",
     "url": "https://pds-geosciences.wustl.edu/mer/mer1_mer2-m-apxs-5-oxide-sci-v1/",
     "used_for": "Spirit and Opportunity rock and soil chemistry",
     "licence": "Public domain"},
    {"id": "csa_apxs", "agency": "CSA", "kind": "dataset",
     "name": "Alpha Particle X-Ray Spectrometer (APXS) carried on board the Curiosity rover",
     "product": "CSA Open Data: APXS RDR files for sols 46-1645 and the PFM2008 lab calibration standards",
     "provider": "Canadian Space Agency (Curiosity's APXS is Canada's contribution to the mission)",
     "url": "https://data.asc-csa.gc.ca/en/dataset/4596426-1c8f-3l9j-895mmct858mg42",
     "used_for": "Oxide and spectrum files for early Curiosity measurements, and 10 Earth reference rocks measured "
                 "by the flight instrument before launch (the 'Earth analogue' comparison)",
     "licence": "Open Government Licence - Canada"},
    {"id": "ody_grs", "agency": "NASA", "kind": "dataset",
     "name": "Mars Odyssey Gamma Ray Spectrometer element concentration maps",
     "product": "ODY-M-GRS-5-ELEMENTS-V1.0, smoothed 5x5 degree tables: Cl, Fe, Si, K, Th, H2O",
     "provider": "NASA PDS Geosciences Node (Boynton et al. 2007, JGR 112, E12S99)",
     "url": "https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/",
     "used_for": "Element concentration maps, prospect zones, water and soil forecasts",
     "licence": "Public domain"},
    {"id": "mola", "agency": "NASA", "kind": "dataset",
     "name": "Mars Global Surveyor MOLA elevation",
     "product": "Mars_MGS_MOLA_DEM_mosaic_global_463m_8 (NASA Mars Trek tiles)",
     "provider": "NASA/JPL-Caltech Mars Trek; MOLA Science Team; USGS Astrogeology",
     "url": "https://trek.nasa.gov/mars/",
     "used_for": "Terrain on the globe, elevations, and the 'low ground' rule for salt-basin prospect zones",
     "licence": "NASA public data"},
    {"id": "gale_dem", "agency": "NASA", "kind": "dataset",
     "name": "MRO HiRISE Gale Crater DEM",
     "product": "Gale_DEM_SMG_1m (NASA Mars Trek), read at zoom 12 (~10 m per pixel)",
     "provider": "NASA/JPL-Caltech Mars Trek; MRO HiRISE (NASA/JPL/University of Arizona)",
     "url": "https://trek.nasa.gov/mars/",
     "used_for": "Terrain for the EVA planner; its height scale is fitted to Curiosity's waypoint elevations",
     "licence": "NASA public data"},
    {"id": "msl_waypoints", "agency": "NASA", "kind": "dataset",
     "name": "Curiosity rover waypoints",
     "product": "MSL_waypoints.json and MSL_traverse.json (MMGIS 'Where is Curiosity' map layers)",
     "provider": "NASA/JPL-Caltech",
     "url": "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json",
     "used_for": "Where each Curiosity measurement was taken (rover position at the start of that sol), and the traverse",
     "licence": "NASA public data"},
    {"id": "mer_traverse", "agency": "NASA", "kind": "dataset",
     "name": "MER corrected traverses",
     "product": "MERA_traverse.csv, MERB_traverse_5130.csv (PDS MER Analyst's Notebook; T. Parker, JPL)",
     "provider": "NASA PDS Geosciences Node",
     "url": "https://an.rsl.wustl.edu/mera/AN/pages/mer/mer_traverse.htm",
     "used_for": "Where each Spirit and Opportunity measurement was taken, and the traverses",
     "licence": "NASA PDS"},
    {"id": "rover_images", "agency": "NASA", "kind": "imagery",
     "name": "Rover close-up images",
     "product": "Curiosity MAHLI raw images (mars.nasa.gov raw image API); MER Microscopic Imager (PDS Imaging Node)",
     "provider": "NASA/JPL-Caltech/MSSS; NASA/JPL/Cornell/USGS",
     "url": "https://science.nasa.gov/mission/msl-curiosity/",
     "used_for": "Photos of each measured rock, loaded on demand",
     "licence": "NASA public data"},
    {"id": "trek_imagery", "agency": "NASA", "kind": "imagery",
     "name": "NASA Mars Trek map tiles",
     "product": "Viking MDIM 2.1 colour mosaic, MOLA colour relief, Odyssey THEMIS day IR, HiRISE rover-site mosaics, "
                "Viking Phobos mosaic",
     "provider": "NASA/JPL-Caltech; USGS; ASU; University of Arizona",
     "url": "https://trek.nasa.gov/mars/",
     "used_for": "The globe's imagery, streamed live",
     "licence": "NASA public data"},
    {"id": "ctx", "agency": "NASA", "kind": "imagery",
     "name": "MRO CTX global mosaic",
     "product": "NASA Mars Trek layer CTX_beta01_uncontrolled_5m_Caltech",
     "provider": "NASA/JPL/MSSS images (Mars Reconnaissance Orbiter); mosaic assembled by Caltech's Murray Lab; "
                 "tiles served from the address NASA Mars Trek lists for the layer",
     "url": "https://trek.nasa.gov/mars/",
     "used_for": "Sharpening the globe between the planet-wide Viking view and the HiRISE rover sites",
     "licence": "NASA public data, credit required"},
    {"id": "sam", "agency": "NASA", "kind": "reference",
     "name": "Curiosity SAM soil-water result",
     "product": "About 2 wt% water released when Gale soil was heated to 835 C (Leshin et al. 2013)",
     "provider": "NASA",
     "url": "https://www.nasa.gov/solar-system/curiositys-sam-instrument-finds-water-and-more-in-surface-sample/",
     "used_for": "The 'practical' share in the extractable-water estimate",
     "licence": "NASA public information"},
    {"id": "nasa_pages", "agency": "NASA", "kind": "reference",
     "name": "NASA and JPL mission pages and news releases",
     "product": "Curiosity, MER and Odyssey mission pages; JPL releases on veins, silica, clays, 'blueberries', the "
                "sulfate unit and boxwork; NASA's Phobos page; Mars24 sun-position algorithm (NASA GISS)",
     "provider": "NASA/JPL-Caltech; NASA GISS",
     "url": "https://science.nasa.gov/mars/",
     "used_for": "The 'why' links, landing-site facts, Phobos dimensions and the day/night line",
     "licence": "NASA public information"},
]


def with_counts(rocks: list[dict], earth_refs: list[dict], grs: dict) -> list[dict]:
    """Attach what was actually loaded from each dataset."""
    by = {}
    for r in rocks:
        by[r["rover"]] = by.get(r["rover"], 0) + 1
    csa_files = sum(1 for r in rocks if (r.get("source", {}).get("rwp") or {}).get("from") == "CSA")
    spectra = sum(1 for r in rocks if "rsp" in r.get("source", {}))
    loaded = {
        "msl_apxs": f"{by.get('Curiosity', 0):,} measurements, {spectra:,} with a linked spectrum",
        "mer_apxs": f"{by.get('Spirit', 0):,} Spirit and {by.get('Opportunity', 0):,} Opportunity measurements",
        "csa_apxs": f"{csa_files:,} Curiosity measurements read from CSA files; {len(earth_refs)} Earth reference standards",
        "ody_grs": ", ".join(f"{k} {len(v['cells']):,} cells" for k, v in grs.items()) if grs else None,
        "mola": "2048 x 1024 px elevation grid for zone rules; live tiles for terrain",
        "gale_dem": "255 tiles over Curiosity's area; height scale fitted to 1,768 waypoint elevations",
        "msl_waypoints": f"positions for {by.get('Curiosity', 0):,} measurements",
        "mer_traverse": f"positions for {by.get('Spirit', 0) + by.get('Opportunity', 0):,} measurements",
    }
    return [{**s, "loaded": loaded.get(s["id"])} for s in SOURCES]
