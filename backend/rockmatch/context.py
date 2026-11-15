"""Plain-language context for a measurement: why its chemistry looks the way it does, where it was
found, and NASA pages to read more. Explanations are standard interpretations from the APXS/rover
literature, phrased as likely causes - chemistry alone cannot prove a formation process."""
from __future__ import annotations

import math

from .chemistry import OXIDES, TRACES

# NASA / JPL pages (each checked to exist)
LINKS = {
    "msl": {"title": "NASA: Curiosity rover mission", "url": "https://science.nasa.gov/mission/msl-curiosity/"},
    "mer": {"title": "NASA: Spirit and Opportunity rovers", "url": "https://science.nasa.gov/mission/mars-exploration-rovers-spirit-and-opportunity/"},
    "vein": {"title": "JPL: NASA Mars rover finds mineral vein deposited by water (2011)",
             "url": "https://www.jpl.nasa.gov/news/nasa-mars-rover-finds-mineral-vein-deposited-by-water/"},
    "silica": {"title": "JPL: Rocks rich in silica present puzzles for Mars rover team (2015)",
               "url": "https://www.jpl.nasa.gov/news/rocks-rich-in-silica-present-puzzles-for-mars-rover-team/"},
    "salty": {"title": "JPL: Curiosity reaches long-awaited salty region (2022)",
              "url": "https://www.jpl.nasa.gov/news/nasas-curiosity-mars-rover-reaches-long-awaited-salty-region/"},
    "clay": {"title": "JPL: Mars rover Opportunity examines clay clues in rock (2013)",
             "url": "https://www.jpl.nasa.gov/news/mars-rover-opportunity-examines-clay-clues-in-rock/"},
    "berries": {"title": "JPL: Mineral in Mars 'berries' adds to water story (2004)",
                "url": "https://www.jpl.nasa.gov/news/mineral-in-mars-berries-adds-to-water-story/"},
    "boxwork": {"title": "JPL: Curiosity starts unpacking boxwork formations (2025)",
                "url": "https://www.jpl.nasa.gov/news/nasas-curiosity-mars-rover-starts-unpacking-boxwork-formations/"},
    "mars": {"title": "NASA: Mars overview", "url": "https://science.nasa.gov/mars/"},
}

CLASS_WHY = {
    "iron_meteorite": ("Metallic iron-nickel this rich does not form on Mars's surface: it is a meteorite, the core of a "
                       "shattered asteroid that landed here. Its Ni:Fe ratio is a fingerprint of that origin.", None),
    "silica": ("Silica this pure needs a lot of water. It is left either when acidic water or steam strips out "
               "everything else, or when silica-rich hot water precipitates opal - as at hot springs on Earth.", "silica"),
    "silica_enriched": ("Fluids moving along fractures added silica (or leached other elements), forming pale "
                        "'halos' around cracks after the sediments had already hardened.", "silica"),
    "ca_sulfate": ("Groundwater carrying dissolved calcium and sulfate flowed through cracks and precipitated "
                   "gypsum or bassanite - a near-neutral water environment, friendlier to life than acidic brines.", "vein"),
    "mn_rich": ("Manganese oxides only precipitate from strongly oxidizing water, so this enrichment hints at "
                "oxygen-bearing groundwater or past atmosphere conditions.", None),
    "al_clay": ("Aluminium and silica stayed behind while water carried away iron, magnesium and calcium - the "
                "signature of clay minerals formed by prolonged, fairly gentle water alteration.", "clay"),
    "mg_sulfate": ("Magnesium sulfate salts are what remain when salty lake or ground water evaporates; these layers "
                   "record Mars drying out.", "salty"),
    "fe_sulfate": ("Ferric sulfates form when acidic, sulfur-rich (often volcanic or hydrothermal) water alters "
                   "iron-bearing rock.", "salty"),
    "sulfate": ("The rock is cemented by sulfate salts that crystallized from evaporating or circulating water.", "salty"),
    "phosphate": ("Phosphorus-rich minerals such as apatite are concentrated here, by igneous processes or by water "
                  "redistributing phosphate - a nutrient life needs.", None),
    "halide": ("Chlorine and bromine end up in salts when brines evaporate; bromine is very mobile in water, so high "
               "or variable Br marks where water last pooled or soaked.", "salty"),
    "zinc": ("Zinc is carried by warm, hydrothermal fluids and deposited where they cool or react with the rock.", None),
    "hematite": ("Iron oxides such as hematite form when iron is oxidized by water - Opportunity's 'blueberries' are "
                 "concretions grown inside water-soaked sediment.", "berries"),
    "alkali": ("Sodium and potassium feldspars point to magma that evolved (partly crystallized) before erupting - "
               "more Earth-like than typical Mars basalt.", None),
    "ultramafic": ("Magnesium-rich olivine (or Mg-carbonate formed from it by warm water) makes up much of this rock.", None),
    "basaltic_soil": ("Ordinary Martian soil: basaltic sand mixed with fine, oxidized dust that winds spread across "
                      "the whole planet.", None),
    "basaltic": ("Typical Martian bedrock: basalt, or sediment eroded from basalt, without strong signs of later "
                 "water enrichment.", None),
}

# (element, threshold ratio vs typical Mars, direction, explanation)
DRIVERS = [
    ("SO3", 2.0, "up", "sulfate salts precipitated from water"),
    ("Cl", 2.0, "up", "chloride salts left by evaporating brines"),
    ("Br", 3.0, "up", "bromide salts - bromine moves easily with water"),
    ("SiO2", 1.25, "up", "silica added by fluids, or left behind by leaching"),
    ("FeO", 1.4, "up", "iron oxides (e.g. hematite) or iron-rich minerals"),
    ("FeO", 0.5, "down", "iron removed by water leaching"),
    ("MnO", 3.0, "up", "manganese oxides - need oxidizing water"),
    ("P2O5", 2.5, "up", "phosphate minerals such as apatite"),
    ("MgO", 1.6, "up", "olivine, or Mg-sulfate / Mg-carbonate"),
    ("MgO", 0.4, "down", "magnesium leached away"),
    ("CaO", 1.8, "up", "calcium sulfate or carbonate cement"),
    ("Al2O3", 1.4, "up", "feldspar or aluminium-rich clay"),
    ("Na2O", 1.8, "up", "sodium feldspar or sodium salts"),
    ("K2O", 2.5, "up", "potassium feldspar from evolved magma"),
    ("Zn", 3.0, "up", "zinc deposited by hydrothermal fluids"),
    ("Ni", 3.0, "up", "meteoritic metal or nickel sulfides"),
]


def drivers(chem: dict, reference: dict, limit: int = 4) -> list[dict]:
    """Elements most enriched/depleted vs the median of all measurements, with a likely cause."""
    found = {}
    for el, thr, direction, why in DRIVERS:
        v, ref = chem.get(el), reference.get(el)
        if v is None or not ref:
            continue
        ratio = v / ref
        if (direction == "up" and ratio >= thr) or (direction == "down" and ratio <= thr):
            score = abs(math.log(max(ratio, 1e-3)))
            if el not in found or score > found[el]["score"]:
                found[el] = {"element": el, "ratio": round(ratio, 2), "direction": direction, "why": why,
                             "value": v, "unit": "ppm" if el in TRACES else "wt%", "score": score}
    out = sorted(found.values(), key=lambda d: -d["score"])[:limit]
    for d in out:
        d.pop("score")
    return out


def region(rover: str, sol: int) -> dict:
    """Coarse geological setting by rover and sol (approximate sol ranges)."""
    if rover == "Curiosity":
        if sol >= 4550:
            return {"name": "Boxwork region, Mount Sharp", "note": "Ridges hardened by ancient groundwater, studied from mid-2025.",
                    "links": [LINKS["boxwork"], LINKS["msl"]]}
        if sol >= 3600:
            return {"name": "Sulfate-bearing unit, Mount Sharp", "note": "Salty layers that record Mars drying out.",
                    "links": [LINKS["salty"], LINKS["msl"]]}
        if sol >= 750:
            return {"name": "Lower Mount Sharp, Gale Crater", "note": "Lake mudstones and sandstones of an ancient crater lake.",
                    "links": [LINKS["msl"]]}
        return {"name": "Gale Crater floor", "note": "River and lake deposits near the landing site.", "links": [LINKS["msl"]]}
    if rover == "Spirit":
        if sol >= 160:
            return {"name": "Columbia Hills, Gusev Crater", "note": "Older, water-altered rocks; Home Plate's silica deposits.",
                    "links": [LINKS["mer"]]}
        return {"name": "Gusev Crater plains", "note": "Volcanic basalt plains around the landing site.", "links": [LINKS["mer"]]}
    if rover == "Opportunity":
        if sol >= 2681:
            return {"name": "Endeavour Crater rim, Meridiani", "note": "Ancient crater rim with gypsum veins and clay-bearing rock.",
                    "links": [LINKS["clay"], LINKS["vein"], LINKS["mer"]]}
        return {"name": "Meridiani Planum", "note": "Sulfate-rich sandstones and hematite 'blueberries' from ancient groundwater.",
                "links": [LINKS["berries"], LINKS["mer"]]}
    return {"name": "Mars", "note": "", "links": [LINKS["mars"]]}


def explain(deposit: str, chem: dict, reference: dict, rover: str | None = None, sol: int | None = None) -> dict:
    why, link_key = CLASS_WHY.get(deposit, ("", None))
    out = {"why": why, "drivers": drivers(chem, reference),
           "links": [LINKS[link_key]] if link_key else [],
           "caveat": "Likely explanations based on bulk chemistry; minerals are not identified directly by APXS."}
    if rover:
        out["region"] = region(rover, sol or 0)
        for link in out["region"]["links"]:
            if link not in out["links"]:
                out["links"].append(link)
    return out
