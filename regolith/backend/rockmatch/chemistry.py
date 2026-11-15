"""APXS chemistry: element lists, units, X-ray lines and rule-based deposit classes.

The deposit classes are a transparent, rule-based *screening* of bulk chemistry,
built from compositional signatures reported in the MER and MSL APXS literature
(e.g. Ca-sulfate veins, opaline silica, Mn-oxide enrichments, iron meteorites).
They flag where a measurement is chemically unusual; they are not a mineral
identification. Every class records the values that triggered it.
"""
from __future__ import annotations

import math

OXIDES = ["Na2O", "MgO", "Al2O3", "SiO2", "P2O5", "SO3", "Cl", "K2O", "CaO", "TiO2", "Cr2O3", "MnO", "FeO"]
TRACES = ["Ni", "Zn", "Br"]
ELEMENTS = OXIDES + TRACES
UNITS = {**{e: "wt%" for e in OXIDES}, **{e: "ppm" for e in TRACES}}
LIMITS = {**{e: (0.0, 100.0) for e in OXIDES}, **{e: (0.0, 300000.0) for e in TRACES}}

# K-alpha X-ray line energies (keV) of the elements APXS reports.
XRAY_LINES = {
    "Na": 1.041, "Mg": 1.254, "Al": 1.487, "Si": 1.740, "P": 2.013, "S": 2.307, "Cl": 2.622,
    "K": 3.314, "Ca": 3.692, "Ti": 4.511, "Cr": 5.415, "Mn": 5.899, "Fe": 6.404,
    "Ni": 7.478, "Zn": 8.639, "Br": 11.924,
}

# Ordered: the first matching rule wins. `notable` classes are highlighted on the map.
DEPOSIT_CLASSES = [
    {"id": "iron_meteorite", "label": "Iron meteorite", "color": "#eceff1", "notable": True,
     "rule": "Ni ≥ 10,000 ppm and FeO ≥ 40 wt%",
     "description": "Iron-nickel metal that fell from space (Curiosity's Cururu and Allison Mine)."},
    {"id": "silica", "label": "Opaline silica", "color": "#84ffff", "notable": True,
     "rule": "SiO2 ≥ 65 wt% with Na2O + K2O < 5 wt%",
     "description": "Nearly pure silica, a signature of hot springs or acid leaching (Spirit's Kenosha Comets, Curiosity's Buckskin)."},
    {"id": "ca_sulfate", "label": "Calcium-sulfate vein", "color": "#fff59d", "notable": True,
     "rule": "SO3 ≥ 18, CaO ≥ 12 wt% and CaO/SO3 = 0.45–1.1 (≈ CaSO4)",
     "description": "Gypsum or bassanite precipitated by groundwater in fractures (Opportunity's Homestake, Curiosity's white veins)."},
    {"id": "mn_rich", "label": "Manganese-enriched", "color": "#b388ff", "notable": True,
     "rule": "MnO ≥ 1.5 wt% (≈ 4× typical Mars)",
     "description": "Manganese oxides need strongly oxidizing water to form - a key clue about past habitability."},
    {"id": "al_clay", "label": "Aluminous clay-like", "color": "#ea80fc", "notable": True,
     "rule": "Al2O3 ≥ 10, SiO2 ≥ 50, FeO ≤ 10, CaO ≤ 6 and Na2O + K2O < 4.5 wt%",
     "description": "Leached, aluminium-rich rock consistent with clay minerals formed in water (Opportunity's Esperance)."},
    {"id": "silica_enriched", "label": "Silica-enriched halo", "color": "#00b8d4", "notable": True,
     "rule": "SiO2 55–65 wt% with Na2O + K2O < 5 wt%",
     "description": "Rock altered by fluids that added silica, often along fractures (Curiosity's Lubango halos)."},
    {"id": "mg_sulfate", "label": "Magnesium-sulfate-rich", "color": "#69f0ae", "notable": True,
     "rule": "SO3 ≥ 15, MgO ≥ 10 wt%, MgO/SO3 ≥ 0.35 and CaO < 8 wt%",
     "description": "Mg-sulfate salts left as lakes and groundwater evaporated (Curiosity's sulfate-bearing unit)."},
    {"id": "fe_sulfate", "label": "Iron-sulfate-rich", "color": "#ffab40", "notable": True,
     "rule": "SO3 ≥ 20 and FeO ≥ 20 wt%",
     "description": "Ferric sulfates from acid-sulfate alteration (Spirit's bright Paso Robles soils)."},
    {"id": "sulfate", "label": "Sulfate-rich sediment", "color": "#ffd740", "notable": True,
     "rule": "SO3 ≥ 12 wt%",
     "description": "Sedimentary rock cemented by sulfate salts (Meridiani's Burns formation)."},
    {"id": "phosphate", "label": "Phosphate-rich", "color": "#448aff", "notable": True,
     "rule": "P2O5 ≥ 2.5 wt% (≈ 3× typical Mars)",
     "description": "Phosphorus-rich rocks such as Spirit's Wishstone class; phosphorus is a nutrient for life."},
    {"id": "halide", "label": "Salt / halogen-enriched", "color": "#8c9eff", "notable": True,
     "rule": "Cl ≥ 2.5 wt% or Br ≥ 1,500 ppm",
     "description": "Chloride and bromide salts concentrated by evaporating brines."},
    {"id": "zinc", "label": "Zinc-enriched", "color": "#ff8a65", "notable": True,
     "rule": "Zn ≥ 3,000 ppm (≈ 10× typical Mars soil)",
     "description": "Zinc concentrated by hydrothermal or groundwater fluids (e.g. Curiosity's Kimberley sandstones)."},
    {"id": "hematite", "label": "Iron-oxide-rich", "color": "#ff5252", "notable": True,
     "rule": "FeO ≥ 24 wt%",
     "description": "Iron-oxide rich material such as Opportunity's hematite 'blueberries'."},
    {"id": "alkali", "label": "Alkali-rich igneous", "color": "#ff80ab", "notable": True,
     "rule": "Na2O + K2O ≥ 5 wt% and SiO2 ≥ 46 wt%",
     "description": "Feldspar-rich igneous rock, more evolved than typical Mars basalt (Curiosity's Jake_M)."},
    {"id": "ultramafic", "label": "Olivine / Mg-rich", "color": "#c6ff00", "notable": True,
     "rule": "MgO ≥ 13 wt%",
     "description": "Olivine- or carbonate-rich rocks high in magnesium (Spirit's Comanche outcrop)."},
    {"id": "basaltic_soil", "label": "Basaltic soil & dust", "color": "#b08d7a", "notable": False,
     "rule": "Soil or sand without the signatures above",
     "description": "Global Mars soil: basaltic sand mixed with fine oxidized dust."},
    {"id": "basaltic", "label": "Basaltic rock / sediment", "color": "#7d6155", "notable": False,
     "rule": "Rock without the signatures above",
     "description": "Typical Mars bedrock: basalt and basalt-derived sandstones and mudstones."},
]
CLASS_BY_ID = {c["id"]: c for c in DEPOSIT_CLASSES}


def num(chem: dict, key: str) -> float | None:
    v = chem.get(key)
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


def clean_chemistry(raw: dict) -> dict:
    """Keep known elements with finite values inside physical limits."""
    out = {}
    for el in ELEMENTS:
        v = raw.get(el)
        if v is None or v == "":
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        lo, hi = LIMITS[el]
        if math.isfinite(v) and lo <= v <= hi:
            out[el] = v
    return out


def classify(chem: dict, sample_type: str | None = None) -> tuple[str, str]:
    """Return (class_id, reason) for a composition. sample_type: 'soil', 'rock', ..."""
    g = lambda k: num(chem, k)  # noqa: E731
    si, s, ca, mg, fe, mn = g("SiO2"), g("SO3"), g("CaO"), g("MgO"), g("FeO"), g("MnO")
    p, cl, na, k, ni, zn, br = g("P2O5"), g("Cl"), g("Na2O"), g("K2O"), g("Ni"), g("Zn"), g("Br")
    al = g("Al2O3")

    if ni is not None and fe is not None and ni >= 10000 and fe >= 40:
        return "iron_meteorite", f"Ni {ni:,.0f} ppm with FeO {fe:.1f} wt%"
    alk = (na or 0) + (k or 0)   # silica deposits and alteration halos are leached of Na and K
    if si is not None and si >= 65 and alk < 5:
        return "silica", f"SiO2 {si:.1f} wt%"
    if s is not None and ca is not None and s >= 18 and ca >= 12 and 0.45 <= ca / s <= 1.1:
        return "ca_sulfate", f"SO3 {s:.1f} and CaO {ca:.1f} wt% (CaO/SO3 {ca / s:.2f})"
    if mn is not None and mn >= 1.5:
        return "mn_rich", f"MnO {mn:.2f} wt%"
    if (al is not None and si is not None and fe is not None and al >= 10 and si >= 50 and fe <= 10
            and (ca is None or ca <= 6) and (na or 0) + (k or 0) < 4.5):
        return "al_clay", f"Al2O3 {al:.1f} and SiO2 {si:.1f} wt% with low FeO {fe:.1f} wt%"
    if si is not None and si >= 55 and alk < 5:
        return "silica_enriched", f"SiO2 {si:.1f} wt%"
    if s is not None and mg is not None and s >= 15 and mg >= 10 and mg / s >= 0.35 and (ca is None or ca < 8):
        return "mg_sulfate", f"SO3 {s:.1f} and MgO {mg:.1f} wt%"
    if s is not None and fe is not None and s >= 20 and fe >= 20:
        return "fe_sulfate", f"SO3 {s:.1f} and FeO {fe:.1f} wt%"
    if s is not None and s >= 12:
        return "sulfate", f"SO3 {s:.1f} wt%"
    if p is not None and p >= 2.5:
        return "phosphate", f"P2O5 {p:.2f} wt%"
    if (cl is not None and cl >= 2.5) or (br is not None and br >= 1500):
        parts = ([f"Cl {cl:.2f} wt%"] if cl is not None and cl >= 2.5 else []) + \
                ([f"Br {br:,.0f} ppm"] if br is not None and br >= 1500 else [])
        return "halide", " and ".join(parts)
    if zn is not None and zn >= 3000:
        return "zinc", f"Zn {zn:,.0f} ppm"
    if fe is not None and fe >= 24:
        return "hematite", f"FeO {fe:.1f} wt%"
    if na is not None and k is not None and si is not None and na + k >= 5 and si >= 46:
        return "alkali", f"Na2O + K2O {na + k:.1f} wt% at SiO2 {si:.1f} wt%"
    if mg is not None and mg >= 13:
        return "ultramafic", f"MgO {mg:.1f} wt%"
    if sample_type in ("soil",):
        return "basaltic_soil", "No unusual enrichments (soil)"
    return "basaltic", "No unusual enrichments"


# ---------------------------------------------------------------------------- map colour views
# The map shows one "view" at a time; everything outside the view's groups is neutral grey.
# Slots 1-3 validate all-pairs (any two points side by side) in dark mode, so the detailed views use at
# most three. The overview colours the five deposit families with slots 1-5 (validated adjacent: CVD
# dE >= 8.4, normal-vision >= 19.3); it always ships with names (legend, hover, family labels) and a
# per-family toggle, because slots 2 and 4 (orange, yellow) can be confused when they sit side by side.
SLOT_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]
OTHER_COLOR = "#898781"
NOTABLE_IDS = [c["id"] for c in DEPOSIT_CLASSES if c["notable"]]
MAP_VIEWS = [
    {"id": "unusual", "label": "All deposits by family", "groups": []},   # filled in below
    {"id": "sulfates", "label": "Sulfate salts & veins", "groups": [
        {"label": "Calcium-sulfate veins", "classes": ["ca_sulfate"]},
        {"label": "Magnesium sulfates", "classes": ["mg_sulfate"]},
        {"label": "Other sulfate-rich (incl. iron sulfates)", "classes": ["sulfate", "fe_sulfate"]}]},
    {"id": "silica", "label": "Silica & clay", "groups": [
        {"label": "Opaline silica", "classes": ["silica"]},
        {"label": "Silica-enriched halos", "classes": ["silica_enriched"]},
        {"label": "Aluminous clay-like", "classes": ["al_clay"]}]},
    {"id": "metals", "label": "Iron, manganese & zinc", "groups": [
        {"label": "Iron-rich (oxides & meteorites)", "classes": ["hematite", "iron_meteorite"]},
        {"label": "Manganese-enriched", "classes": ["mn_rich"]},
        {"label": "Zinc-enriched", "classes": ["zinc"]}]},
    {"id": "halogens", "label": "Halogens & phosphorus", "groups": [
        {"label": "Salt / halogen-enriched", "classes": ["halide"]},
        {"label": "Phosphate-rich", "classes": ["phosphate"]}]},
    {"id": "igneous", "label": "Igneous rock types", "groups": [
        {"label": "Alkali-rich igneous", "classes": ["alkali"]},
        {"label": "Olivine / Mg-rich", "classes": ["ultramafic"]}]},
]
MAP_VIEWS[0]["groups"] = [{"label": v["label"], "classes": [c for g in v["groups"] for c in g["classes"]]}
                          for v in MAP_VIEWS[1:]]
CLASS_FAMILY = {cid: v["id"] for v in MAP_VIEWS[1:] for g in v["groups"] for cid in g["classes"]}
assert sorted(CLASS_FAMILY) == sorted(NOTABLE_IDS), "every deposit class needs exactly one family"
