"""API tests against the built dataset (backend/data/*.json)."""
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"
ROVERS = {"Curiosity", "Spirit", "Opportunity"}


def find(rocks, rover, name_part):
    return next(r for r in rocks if r["rover"] == rover and name_part.lower() in r["name"].lower())


# ------------------------------------------------------------------ dataset & metadata

def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["rocks_loaded"] > 2400
    assert h["deposit_sites"] > 100
    assert h["earth_refs"] == 10


def test_meta(client):
    m = client.get("/api/meta").json()
    assert set(m["sites"]) == ROVERS
    assert {c["id"] for c in m["classes"]} >= {"silica", "ca_sulfate", "basaltic"}
    assert "CSA" in m["citations"] and "Open Government Licence" in m["citations"]["CSA"]
    assert sum(c["count"] for c in m["classes"]) == m["count"]


def test_every_rock_is_complete(rocks):
    ids = set()
    for r in rocks:
        assert r["id"] not in ids
        ids.add(r["id"])
        assert r["rover"] in ROVERS
        assert -90 <= r["lat"] <= 90 and -180 <= r["lon"] < 180
        assert sum(k in r["chemistry"] for k in ("SiO2", "FeO", "MgO", "CaO", "Al2O3")) == 5
        assert r["deposit"] and r["deposit_reason"]
        assert r["quality"]["tier"] in ("good", "fair", "quick-look")


def test_rocks_stay_near_their_rover_site(client, rocks):
    sites = client.get("/api/meta").json()["sites"]
    for r in rocks:
        s = sites[r["rover"]]
        assert abs(r["lat"] - s["lat"]) < 1.0 and abs(r["lon"] - s["lon"]) < 1.0, r["id"]


def test_curiosity_rocks_link_to_pds_or_csa_files(rocks):
    msl = [r for r in rocks if r["rover"] == "Curiosity"]
    linked = [r for r in msl if "rwp" in r["source"]]
    assert len(linked) / len(msl) > 0.98
    assert {r["source"]["rwp"]["from"] for r in linked} == {"CSA", "PDS"}
    assert all(r["source"]["link_mean_abs_diff_wt"] <= 1.5 for r in linked)


# ------------------------------------------------------------------ rock endpoints

def test_rock_list_filters(client):
    spirit = client.get("/api/rocks", params={"rover": "spirit"}).json()
    assert spirit["total"] == 220 and all(r["rover"] == "Spirit" for r in spirit["rocks"])
    silica = client.get("/api/rocks", params={"deposit": "silica"}).json()
    assert silica["total"] > 5 and all(r["deposit"] == "silica" for r in silica["rocks"])
    q = client.get("/api/rocks", params={"q": "homestake"}).json()
    assert q["total"] >= 1
    page = client.get("/api/rocks", params={"limit": 10, "offset": 5}).json()
    assert page["count"] == 10
    assert client.get("/api/rocks", params={"quality": "excellent"}).status_code == 422


def test_rock_detail(client, rocks):
    homestake = find(rocks, "Opportunity", "Homestake")
    d = client.get(f"/api/rocks/{homestake['id']}").json()
    assert d["deposit"] == "ca_sulfate" and d["class"]["label"] == "Calcium-sulfate vein"
    assert len(d["similar"]) == 5 and all(s["id"] != homestake["id"] for s in d["similar"])
    assert d["earth_ref"]["name"]
    assert d["has_spectrum"] is False
    assert client.get("/api/rocks/not-a-rock").status_code == 404


def test_rocks_near(client, rocks):
    r = find(rocks, "Curiosity", "Jake Matijevic")
    near = client.get("/api/rocks/near", params={"lat": r["lat"], "lon": r["lon"], "radius_km": 1}).json()
    assert near["count"] >= 1 and near["rocks"][0]["distance_m"] <= 1000
    dists = [x["distance_m"] for x in near["rocks"]]
    assert dists == sorted(dists)


def test_spectrum_from_local_file(client, rocks):
    r = next(r for r in rocks if r["rover"] == "Curiosity" and "rsp" in r["source"])
    if not (DATA / "raw" / r["source"]["rsp"]["file"]).exists():
        pytest.skip("raw spectra not downloaded")
    s = client.get(f"/api/rocks/{r['id']}/spectrum").json()
    assert len(s["energy_kev"]) == len(s["counts"]) > 1000
    assert s["live_time_s"] > 0
    assert "Fe" in s["lines"] and abs(s["lines"]["Fe"] - 6.404) < 1e-6
    assert s["energy_kev"] == sorted(s["energy_kev"])


def test_spectrum_missing_for_mer(client, rocks):
    r = next(r for r in rocks if r["rover"] == "Spirit")
    assert client.get(f"/api/rocks/{r['id']}/spectrum").status_code == 404


def test_photos_degrade_gracefully(client, rocks, monkeypatch):
    import app as app_module

    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(app_module, "rover_photos", boom)
    r = rocks[0]
    res = client.get(f"/api/rocks/{r['id']}/photos")
    assert res.status_code == 200 and res.json()["images"] == [] and "offline" in res.json()["error"]


# ------------------------------------------------------------------ deposits, traverses, references

def test_deposits(client):
    deps = client.get("/api/deposits", params={"notable": True}).json()
    assert deps["count"] > 50
    d = deps["deposits"][0]
    full = client.get(f"/api/deposits/{d['id']}").json()
    assert len(full["rocks"]) == d["count"] == len(d["members"])
    assert all(r["deposit"] == d["class"] for r in full["rocks"])
    assert client.get("/api/deposits/nope").status_code == 404


def test_traverses(client):
    t = client.get("/api/traverses").json()
    assert set(t) == ROVERS
    assert all(len(pts) > 100 for pts in t.values())


def test_earth_refs(client):
    refs = client.get("/api/earth-refs").json()["references"]
    assert len(refs) == 10
    bcr = next(r for r in refs if r["name"] == "BCR-2")
    assert bcr["chemistry"]["SiO2"] == pytest.approx(54.1)
    assert bcr["chemistry"]["FeO"] == pytest.approx(13.8 * 0.8998, rel=1e-3)   # Fe2O3T converted


# ------------------------------------------------------------------ classify & match

def test_classify_endpoint(client):
    res = client.post("/api/classify", json={"chemistry": {"SiO2": 90, "FeO": 1.5, "MgO": 2.3, "Na2O": 0.2}})
    assert res.json()["class"] == "silica"
    assert client.post("/api/classify", json={"chemistry": {"SiO2": 45}}).status_code == 422


def test_match_finds_the_rock_itself(client, rocks):
    homestake = find(rocks, "Opportunity", "Homestake")
    res = client.post("/api/match", json={"chemistry": homestake["chemistry"]}).json()
    assert res["matches"][0]["id"] == homestake["id"]
    assert res["matches"][0]["similarity"] == 100
    assert res["query"]["class"] == "ca_sulfate"
    assert res["verdict"]["label"] in ("SAMPLE", "MAYBE", "DUPLICATE")
    assert res["earth_ref"]["name"]


def test_match_exclude_position_and_filters(client, rocks):
    jake = find(rocks, "Curiosity", "Jake Matijevic")
    body = {"chemistry": jake["chemistry"], "exclude_id": jake["id"], "lat": jake["lat"], "lon": jake["lon"], "top_k": 8}
    res = client.post("/api/match", json=body).json()
    assert len(res["matches"]) == 8 and all(m["id"] != jake["id"] for m in res["matches"])
    assert all(m["distance_m"] is not None for m in res["matches"])
    sims = [m["similarity"] for m in res["matches"]]
    assert sims == sorted(sims, reverse=True)
    assert "nearest_same_class" in res
    only_spirit = client.post("/api/match", json={**body, "rover": "Spirit"}).json()
    assert all(m["rover"] == "Spirit" for m in only_spirit["matches"])


def test_match_novel_rock_is_worth_sampling(client):
    weird = {"SiO2": 20, "FeO": 5, "MgO": 1, "CaO": 1, "Al2O3": 2, "SO3": 2, "MnO": 30, "Cl": 0.1}
    res = client.post("/api/match", json={"chemistry": weird}).json()
    assert res["verdict"]["label"] == "SAMPLE"


@pytest.mark.parametrize("body", [
    {"chemistry": {"SiO2": 45, "FeO": 18}},
    {"chemistry": {"SiO2": 45, "FeO": 18, "MgO": 8}, "lat": 120},
    {"chemistry": {"SiO2": 45, "FeO": 18, "MgO": 8}, "top_k": 0},
    {"chemistry": "not a dict"},
])
def test_match_validation(client, body):
    assert client.post("/api/match", json=body).status_code == 422


# ------------------------------------------------------------------ pages & uploads

def test_pages(client):
    assert client.get("/").status_code == 200
    assert "Regolith" in client.get("/").text
    g = client.get("/globe", follow_redirects=False)
    assert g.status_code in (307, 308)
    assert client.get("/globe/").status_code == 200


# ------------------------------------------------------------------ CTX tile proxy

def test_ctx_tile_proxy_caches_and_degrades(client, monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr(app_module, "CACHE", tmp_path)
    calls = []

    def fake_get(url, timeout=0):
        calls.append(url)
        return b"\x89PNG fake tile"
    monkeypatch.setattr(app_module, "http_get", fake_get)
    first = client.get("/api/tiles/ctx/12/2152/7223.png")
    second = client.get("/api/tiles/ctx/12/2152/7223.png")
    assert first.status_code == second.status_code == 200
    assert first.content == second.content == b"\x89PNG fake tile"
    assert len(calls) == 1 and calls[0].endswith("/tile/12/2152/7223")      # second hit served from disk cache
    assert "max-age" in first.headers["cache-control"]

    def broken(url, timeout=0):
        raise OSError("upstream down")
    monkeypatch.setattr(app_module, "http_get", broken)
    fallback = client.get("/api/tiles/ctx/11/1000/2000.png")
    assert fallback.status_code == 200 and fallback.content == app_module.TRANSPARENT_PNG
    assert fallback.headers["cache-control"] == "no-store"
    assert client.get("/api/tiles/ctx/13/0/0.png").status_code == 404
    assert client.get("/api/tiles/ctx/5/40/0.png").status_code == 404


def test_transparent_png_is_valid():
    import app as app_module
    png = app_module.TRANSPARENT_PNG
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and png.endswith(b"IEND\xaeB`\x82")


# ------------------------------------------------------------------ explanations

def test_rock_context_explains_chemistry(client, rocks):
    homestake = find(rocks, "Opportunity", "Homestake")
    ctx = client.get(f"/api/rocks/{homestake['id']}").json()["context"]
    assert "groundwater" in ctx["why"].lower()
    els = {d["element"]: d for d in ctx["drivers"]}
    assert els["SO3"]["direction"] == "up" and els["SO3"]["ratio"] > 2
    assert ctx["region"]["name"].startswith("Endeavour")
    assert all(l["url"].startswith("https://") and ("nasa.gov" in l["url"]) for l in ctx["links"])


def test_match_query_has_context(client):
    res = client.post("/api/match", json={"chemistry": {"SiO2": 90, "FeO": 1.5, "MgO": 2.3, "Al2O3": 1.7, "CaO": 0.7}}).json()
    assert res["query"]["context"]["why"] and res["query"]["context"]["links"]


# ------------------------------------------------------------------ element concentration maps

def test_element_catalog(client):
    els = {e["key"]: e for e in client.get("/api/elements").json()["elements"]}
    assert els["Cl"]["grs"] and els["Cl"]["apxs_count"] > 2000
    assert els["Th"]["grs"] and els["Th"]["apxs_count"] == 0 and els["Th"]["grs_unit"] == "ppm"
    assert not els["Mn"]["grs"] and els["Mn"]["apxs_field"] == "MnO"


def test_chlorine_map_matches_nasa_tables(client):
    m = client.get("/api/elements/Cl", params={"pct": 90}).json()
    g, a = m["grs"], m["apxs"]
    assert g["unit"] == "wt%" and g["n"] == 1508 and abs(g["max"] - 0.797) < 1e-9 and abs(g["min"] - 0.216) < 1e-9
    assert all(abs(c[0]) <= 57.5 for c in g["cells"])             # non-radioactive maps are masked at the poles
    assert g["n_high"] == sum(1 for c in g["cells"] if c[2] >= g["threshold"])
    assert a["n_high"] == sum(1 for _, v in a["values"] if v >= a["threshold"])
    top = a["hotspots"][0]
    assert top["top_name"] == "Kythira" and abs(top["max"] - 19.75) < 1e-9
    for h in a["hotspots"]:
        assert all(v >= a["threshold"] for i, v in a["values"] if i in h["ids"])


def test_element_validation(client):
    assert client.get("/api/elements/Xx").status_code == 404
    assert client.get("/api/elements/Cl", params={"pct": 30}).status_code == 422
    assert client.get("/api/elements/H2O").json()["apxs"] is None


# ------------------------------------------------------------------ GRS accuracy (checked against NASA's tables/maps)

def test_grs_longitude_is_east_positive(client):
    # NASA's browse map: Arabia Terra (~22.5E, 7.5N) is high in H2O, south of Valles (~-62.5E, -37.5) is low
    cells = {(c[0], c[1]): c[2] for c in client.get("/api/elements/H2O?pct=75").json()["grs"]["cells"]}
    assert cells[(7.5, 22.5)] == 6.291 and cells[(-37.5, -62.5)] == 1.993


def test_grs_errors_are_nasa_totals(client):
    cl = {(c[0], c[1]): c[3] for c in client.get("/api/elements/Cl?pct=75").json()["grs"]["cells"]}
    assert cl[(-2.5, 137.5)] == 0.054                      # SIGMA WITH CFS (SIGMA alone is 0.037)
    th = {(c[0], c[1]): c[3] for c in client.get("/api/elements/Th?pct=75").json()["grs"]["cells"]}
    assert th[(87.5, 177.5)] == 0.035                      # CFS not applicable for Th -> SIGMA


def test_rover_sites_compare_orbit_and_ground(client):
    d = client.get("/api/elements/Cl?pct=75").json()
    sites = {s["rover"]: s for s in d["sites"]}
    assert sites["Curiosity"]["grs"]["cell"] == [-2.5, 137.5] and sites["Curiosity"]["grs"]["value"] == 0.583
    assert sites["Spirit"]["grs"]["cell"] == [-12.5, 177.5] and sites["Spirit"]["grs"]["value"] == 0.691
    assert sites["Opportunity"]["grs"]["cell"] == [-2.5, -7.5] and sites["Opportunity"]["grs"]["value"] == 0.571
    assert sites["Curiosity"]["apxs"]["n"] > 1000 and d["grs"]["data_edge"]["north"] == [40.0, 60.0]


def test_percentile_is_nearest_rank():
    from rockmatch.elements import percentile
    assert percentile([1, 2, 3, 4], 50) == 2 and percentile([1, 2, 3, 4], 75) == 3 and percentile([1, 2, 3, 4], 76) == 4


# ------------------------------------------------------------------ prospect zones (orbit-only rules)

def test_prospect_zones_follow_their_rules(client):
    d = client.get("/api/prospects").json()
    assert set(d["kinds"]) == {"salt", "water", "potassium"}
    for kind, k in d["kinds"].items():
        grs = {(c[0], c[1]): c[2] for c in client.get(f"/api/elements/{k['grs']}?pct=75").json()["grs"]["cells"]}
        for z in k["zones"]:
            assert all(grs[(la, lo)] >= k["threshold"] for la, lo in z["cells"])
        if kind == "salt":
            assert all(z["elev_m"] < 0 for z in k["zones"])       # low ground (planet median is about -30 m)
    assert d["links"]["salt"]["url"].startswith("https://www.jpl.nasa.gov/")


def test_prospect_ground_truth(client):
    k = client.get("/api/prospects").json()["kinds"]
    salt = {g["rover"]: g for z in k["salt"]["zones"] for g in z["ground"]}
    water = {g["rover"]: g for z in k["water"]["zones"] for g in z["ground"]}
    assert salt["Curiosity"]["n_related"] > 50                   # Gale's halide-rich rocks sit in a salt zone
    assert water["Opportunity"]["n_related"] > 100               # Meridiani's sulfate sandstones sit in a water zone


def test_mola_decoding_matches_known_elevations():
    from pathlib import Path
    from rockmatch.terrain import elevation_at, load_dem
    folder = Path(__file__).resolve().parents[1] / "data" / "raw" / "trek_mola_dem_z2"
    if not folder.exists():
        import pytest
        pytest.skip("MOLA tiles not downloaded (fetch_data.py --only mola)")
    g = load_dem(folder)
    assert abs(elevation_at(g, -4.5895, 137.4417) - -4501) < 150      # Curiosity landing site
    assert abs(elevation_at(g, -14.5684, 175.4726) - -1940) < 150     # Spirit landing site


# ------------------------------------------------------------------ predictions (estimates beyond the data)

def test_water_yield_maths():
    from rockmatch.predict import water_yield
    w = water_yield(5.0, 5.0)                                  # at Gale itself the practical share is SAM's 2 wt%
    assert w["upper_l_t"] == 50 and w["practical_l_t"] == 20 and w["share"] == 0.4


def test_minerals_follow_formulas():
    from rockmatch.predict import minerals
    gyp = minerals({"CaO": 32.57, "SO3": 46.51})               # pure gypsum (the other 20.9 wt% is water)
    assert gyp["minerals"][0]["formula"] == "CaSO4" and abs(gyp["minerals"][0]["wt"] - 79.1) < 0.2
    salt = minerals({"Na2O": 10.0, "Cl": 15.0})
    assert salt["minerals"][0]["formula"] == "NaCl" and salt["unassigned"]   # more Cl than Na can hold
    assert minerals({"SiO2": 45, "FeO": 18})["minerals"] == []


def test_forecast_endpoint(client):
    g = client.get("/api/forecast?lat=-4.72&lon=137.37").json()          # Gale
    assert {z["kind"] for z in g["zones"]} >= {"salt"} and g["nearby"]["n"] > 50
    assert g["water"]["practical_l_t"] < g["water"]["upper_l_t"] and g["nearby"]["skill"]["top1_pct"] > g["nearby"]["skill"]["baseline_pct"]
    assert all(v <= 30 for v in g["ground"]["check"]["error_pct"].values())
    far = client.get("/api/forecast?lat=30&lon=-100").json()             # no rover anywhere near
    assert far["nearby"] is None and far["ground"]["predicted"]["FeO"] > 0


def test_match_includes_predictions(client):
    r = client.post("/api/match", json={"chemistry": {"SiO2": 16, "SO3": 34, "CaO": 23, "FeO": 12},
                                        "lat": -4.72, "lon": 137.37}).json()
    assert r["query"]["minerals"]["minerals"] and r["query"]["forecast"]["nearby"]


def test_validation_and_sources(client):
    v = client.get("/api/validation").json()
    assert v["matching"]["remeasure_same_type_pct"] > 95 and v["matching"]["remeasure_top5_pct"] > 90
    assert v["nearby"]["log_loss"] < v["nearby"]["log_loss_prior_only"]            # beats the planet-wide mix
    for b in v["nearby"]["calibration"]:
        assert abs(b["predicted_pct"] - b["observed_pct"]) < 5                     # well calibrated
    s = client.get("/api/sources").json()["sources"]
    assert {x["agency"] for x in s} == {"NASA", "CSA"}
    assert all(x["url"].startswith("https://") for x in s)
