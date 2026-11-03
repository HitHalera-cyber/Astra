import cea
import pytest

from astra.core import species_db


def test_database_loaded_completely():
    sp = species_db.load()
    assert len(sp) == 2111
    assert sum(s.reactant_only for s in sp) > 50


def test_known_species_records():
    h2l = species_db.by_name("H2(L)")
    assert h2l.condensed and h2l.phase_name == "жидкость"
    assert h2l.t_assigned == pytest.approx(20.27)
    assert h2l.hf == pytest.approx(-9012.0)
    ch4 = species_db.by_name("CH4")
    assert not ch4.condensed and ch4.molar_mass == pytest.approx(16.04246)
    assert ch4.hf == pytest.approx(-74600.0)
    assert ch4.t_ranges[0] == (200.0, 1000.0)
    assert species_db.by_name("Ag+").formula_text == "Ag⁺"
    assert species_db.by_name("e-").formula_text == "e⁻"


def test_search_ranking():
    found = [s.name for s in species_db.search("h2o")]
    assert found[0] == "H2O"
    assert "H2O(L)" in found[:6]
    assert not any(n.startswith("Inert") for n in found)


def test_every_species_is_known_to_core():
    # база для поиска совпадает с базой, скомпилированной в ядро
    cea.init()
    for s in species_db.load():
        cea.Mixture([s.name])
