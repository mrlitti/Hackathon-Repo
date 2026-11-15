"""Deposit classification of reference compositions (values from published APXS targets)."""
import pytest

from rockmatch.chemistry import CLASS_BY_ID, DEPOSIT_CLASSES, classify, clean_chemistry
from rockmatch.geo import distance_m, wrap_lon
from rockmatch.match import similarity_pct

BASALT = {"Na2O": 2.8, "MgO": 8.5, "Al2O3": 9.5, "SiO2": 45.5, "P2O5": 0.9, "SO3": 5.5, "Cl": 0.7,
          "K2O": 0.45, "CaO": 7.0, "TiO2": 0.9, "Cr2O3": 0.4, "MnO": 0.36, "FeO": 18.5,
          "Ni": 450, "Zn": 300, "Br": 50}


def comp(**over):
    return {**BASALT, **over}


@pytest.mark.parametrize("chem, sample_type, expected", [
    (comp(), "rock", "basaltic"),
    (comp(), "soil", "basaltic_soil"),
    (comp(SiO2=90.5, FeO=1.4, Na2O=0.2, K2O=0.1), "rock", "silica"),                 # Kenosha Comets
    (comp(SiO2=62.5, FeO=5.0), "rock", "silica_enriched"),                           # Buckskin raster
    (comp(SiO2=71.0, Na2O=4.0, K2O=4.5), "rock", "alkali"),                          # granite, not silica
    (comp(SO3=32.7, CaO=22.0, SiO2=20.0), "rock", "ca_sulfate"),                     # Homestake
    (comp(MnO=4.2), "rock", "mn_rich"),
    (comp(Al2O3=15.4, SiO2=62.5, FeO=4.4, CaO=2.1, Na2O=2.0, K2O=0.5), "rock", "al_clay"),  # Esperance
    (comp(SO3=18.0, MgO=12.0, CaO=4.0), "rock", "mg_sulfate"),
    (comp(SO3=31.0, FeO=26.0, CaO=5.0), "soil", "fe_sulfate"),                       # Paso Robles
    (comp(SO3=22.0), "rock", "sulfate"),                                            # Burns formation
    (comp(P2O5=5.2), "rock", "phosphate"),                                          # Wishstone
    (comp(Cl=2.9), "rock", "halide"),
    (comp(Br=2000), "rock", "halide"),
    (comp(Zn=5000), "rock", "zinc"),
    (comp(FeO=28.0), "soil", "hematite"),                                           # blueberry lag
    (comp(Na2O=6.6, K2O=2.0, SiO2=50.0), "rock", "alkali"),                         # Jake_M
    (comp(MgO=25.0), "rock", "ultramafic"),                                         # Comanche
    (comp(FeO=74.0, Ni=53000), "rock", "iron_meteorite"),                           # Cururu
])
def test_classify(chem, sample_type, expected):
    cid, reason = classify(chem, sample_type)
    assert cid == expected, reason
    assert reason


def test_classes_are_complete():
    ids = [c["id"] for c in DEPOSIT_CLASSES]
    assert len(ids) == len(set(ids))
    for c in DEPOSIT_CLASSES:
        assert c["color"].startswith("#") and c["label"] and c["rule"] and c["description"]
    assert set(CLASS_BY_ID) == set(ids)


def test_clean_chemistry_drops_bad_values():
    out = clean_chemistry({"SiO2": "45.1", "FeO": None, "MgO": -3, "CaO": 250, "Ni": "abc", "Zn": 900, "Xx": 4})
    assert out == {"SiO2": 45.1, "Zn": 900.0}


def test_geometry_and_similarity():
    assert wrap_lon(354.4734) == pytest.approx(-5.5266)
    one_deg = distance_m(0, 0, 0, 1)
    assert one_deg == pytest.approx(59158, rel=1e-3)          # 1 degree on Mars ≈ 59.2 km
    assert similarity_pct(0) == 100 and similarity_pct(3) < 2
