"""Проверки адаптера ядра: соотношения, сопло, ошибки, пакетный запуск, обозначения."""

import math

import numpy as np
import pytest

from astra.core import (BAR, QUANTITIES, CeaSession, Component, FUEL, InputError, OXIDIZER, Propellant,
                        Ratio, Task, TaskFailure, classify_regime, grid, run_batch)


@pytest.fixture(scope="module")
def h2o2():
    return Propellant((Component("H2(L)", FUEL, t0=20.27), Component("O2(L)", OXIDIZER, t0=90.17)))


@pytest.fixture(scope="module")
def sess(h2o2):
    return CeaSession(h2o2)


# --- Kм и α ---------------------------------------------------------------

def test_stoichiometric_km_h2_o2(sess):
    # 2 H2 + O2: Kм⁰ = M(O2) / (2·M(H2)) = 31.9988 / 4.03176
    assert sess.km0 == pytest.approx(31.9988 / (2 * 2.01588), rel=1e-6)


def test_km_alpha_roundtrip(sess):
    for a in (0.5, 0.8, 1.0, 1.3):
        km = sess.km(Ratio.alpha(a))
        assert km == pytest.approx(a * sess.km0)
        assert sess.alpha(km) == pytest.approx(a)


def test_alpha_equals_inverse_phi_of_core(sess):
    # Ядро: φ — массовый коэффициент эквивалентности. α = 1/φ по определению.
    import cea
    reac = cea.Mixture(["H2(L)", "O2(L)"])
    km_core = reac.weight_eq_ratio_to_of_ratio(np.array([0, 1.0]), np.array([1.0, 0]), 1 / 0.8)
    assert sess.km(Ratio.alpha(0.8)) == pytest.approx(km_core, rel=1e-10)


def test_mole_basis_matches_mass_basis():
    by_mass = Propellant((Component("CH4", FUEL), Component("O2", OXIDIZER)))
    by_mole = Propellant((Component("CH4", FUEL), Component("O2", OXIDIZER)), basis="mole")
    assert CeaSession(by_mass).km0 == pytest.approx(CeaSession(by_mole).km0)
    assert CeaSession(by_mass).km0 == pytest.approx(2 * 31.9988 / 16.04246, rel=1e-5)


# --- Равновесие -----------------------------------------------------------

def test_hp_with_given_enthalpy_equals_default(sess):
    km = 6.0
    i0 = sess.reactant_property(km, "i")
    a = sess.equilibrium("HP", Ratio.km(km), p=7e6)
    b = sess.equilibrium("HP", Ratio.km(km), p=7e6, i=i0)
    assert a.converged and b.converged
    assert a["t"] == pytest.approx(b["t"], rel=1e-12)
    assert a["i"] == pytest.approx(i0, rel=1e-6)   # энтальпия продуктов = энтальпии компонентов


def test_sp_reproduces_hp_state(sess):
    hp = sess.equilibrium("HP", Ratio.km(6.0), p=7e6)
    sp = sess.equilibrium("SP", Ratio.km(6.0), p=7e6, s=hp["s"])
    assert sp.converged
    assert sp["t"] == pytest.approx(hp["t"], rel=1e-6)


def test_tv_reproduces_tp_state(sess):
    tp = sess.equilibrium("TP", Ratio.km(6.0), p=1e6, t=3000.0)
    tv = sess.equilibrium("TV", Ratio.km(6.0), t=3000.0, v=tp["v"])
    assert tv.converged
    assert tv["p"] == pytest.approx(1e6, rel=1e-6)


def test_nonconvergence_is_reported_not_hidden(sess):
    # энтальпия −50 МДж/кг недостижима для продуктов H2/O2 в диапазоне данных базы
    r = sess.equilibrium("HP", Ratio.km(6.0), p=1e6, i=-5e7)
    assert not r.converged and r.error_code != 0
    assert "сходимост" in r.message
    assert math.isnan(r["t"]) and r.point.mole_fractions == {}


def test_invalid_inputs_have_russian_messages(sess, h2o2):
    with pytest.raises(InputError, match="давлен"):
        sess.equilibrium("TP", Ratio.km(6.0), t=3000.0)
    with pytest.raises(InputError, match="постановк"):
        sess.equilibrium("XY", Ratio.km(6.0), p=1e6)
    with pytest.raises(InputError, match="ε"):
        sess.nozzle(Ratio.km(6.0), 5e6, eps=[0.5])
    with pytest.raises(InputError, match="окислитель"):
        Propellant((Component("H2(L)", FUEL),))
    with pytest.raises(InputError, match="не найдено в базе NASA CEA: Unobtainium"):
        CeaSession(Propellant((Component("Unobtainium", FUEL), Component("O2", OXIDIZER))))
    with pytest.raises(InputError, match="диапазона"):
        CeaSession(Propellant((Component("H2(L)", FUEL, t0=298.15), Component("O2(L)", OXIDIZER, t0=90.17))))


# --- Камера и сопло ------------------------------------------------------

def test_chamber_fixed_across_expansion_ratios(sess):
    one = sess.nozzle(Ratio.km(6.0), 7e6, eps=[10])
    many = sess.nozzle(Ratio.km(6.0), 7e6, eps=[5, 10, 40, 100])
    assert one.chamber["t"] == pytest.approx(many.chamber["t"], rel=1e-12)
    assert one.chamber.mole_fractions["H2O"] == pytest.approx(many.chamber.mole_fractions["H2O"], rel=1e-12)
    isp10 = [p for p in many.exits() if abs(p["eps"] - 10) < 1e-3][0]["isp_vac"]
    assert isp10 == pytest.approx(one.exits()[0]["isp_vac"], rel=1e-6)


def test_total_enthalpy_conserved_along_nozzle(sess):
    r = sess.nozzle(Ratio.km(6.0), 7e6, eps=[2, 10, 50], pk_p=[10])
    h0 = r.chamber["H"]
    for p in r.points:
        assert p["H"] == pytest.approx(h0, rel=1e-6)
        assert p["H"] == pytest.approx(p["i"] + p["w"] ** 2 / 2, rel=1e-12)


def test_isp_at_ambient_equals_core_isp_at_design_pressure(sess):
    base = sess.nozzle(Ratio.km(6.0), 7e6, eps=[30])
    pa = base.exits()[0]["p"]
    r = sess.nozzle(Ratio.km(6.0), 7e6, eps=[30], pn=pa)
    ex = r.exits()[0]
    assert ex["isp_amb"] == pytest.approx(ex["isp"], rel=1e-6)
    assert ex.regime == "design"
    vac = sess.nozzle(Ratio.km(6.0), 7e6, eps=[30], pn=0.0).exits()[0]
    assert vac["isp_amb"] == pytest.approx(vac["isp_vac"], rel=1e-12) and vac.regime == "vacuum"


def test_regime_classification_is_independent_of_chemistry(sess):
    for model in ("equilibrium", "frozen"):
        r = sess.nozzle(Ratio.km(6.0), 7e6, eps=[3, 200], pn=101325.0, model=model)
        small, large = r.exits()
        assert small.regime == "under" and large.regime == "over"
        assert any("отрыв" in w for w in r.warnings)
    assert classify_regime(2.0, 1.0) == "under" and classify_regime(0.5, 1.0) == "over"


def test_frozen_isp_below_equilibrium(sess):
    eq = sess.nozzle(Ratio.km(6.0), 7e6, eps=[50]).exits()[0]
    fr_c = sess.nozzle(Ratio.km(6.0), 7e6, eps=[50], model="frozen", freeze_at="chamber").exits()[0]
    fr_t = sess.nozzle(Ratio.km(6.0), 7e6, eps=[50], model="frozen", freeze_at="throat").exits()[0]
    assert fr_c["isp_vac"] < fr_t["isp_vac"] < eq["isp_vac"]


def test_frozen_at_chamber_keeps_chamber_composition(sess):
    r = sess.nozzle(Ratio.km(6.0), 7e6, eps=[10, 50], model="frozen", freeze_at="chamber")
    xc = r.chamber.mole_fractions
    for p in r.exits():
        for sp in ("H2O", "OH", "H2"):
            assert p.mole_fractions[sp] == pytest.approx(xc[sp], rel=1e-9)


def test_mass_flow_gives_throat_area_and_thrust(sess):
    r = sess.nozzle(Ratio.km(6.0), 7e6, eps=[40], pn=0.0, mdot=10.0)
    ex = r.exits()[0]
    assert ex["f_kr"] == pytest.approx(10.0 * ex["c_star"] / 7e6)
    assert ex["f_a"] == pytest.approx(ex["eps"] * ex["f_kr"])
    assert ex["thrust"] == pytest.approx(ex["isp_vac"] * 10.0)
    assert ex["kt_p"] == pytest.approx(ex["isp_vac"] / ex["c_star"])


def test_tk_given_instead_of_enthalpy(sess):
    r = sess.nozzle(Ratio.km(6.0), 7e6, eps=[10], tk=3000.0)
    assert r.converged and r.chamber["t"] == pytest.approx(3000.0)


def test_finite_area_chamber(sess):
    r = sess.nozzle(Ratio.km(6.0), 7e6, eps=[10], eps_k=2.0)
    kinds = [p.kind for p in r.points]
    assert kinds[:4] == ["injector", "chamber_inf", "chamber_end", "throat"]
    assert r.chamber["p"] < 7e6           # потери полного давления в камере конечной площади
    assert r.throat["M"] == pytest.approx(1.0, abs=1e-4)


# --- Сетки и пакетный запуск ---------------------------------------------

def test_grids():
    assert np.allclose(grid.by_step(2, 3, 0.25), [2, 2.25, 2.5, 2.75, 3])
    assert np.allclose(grid.by_step(1, 2, 0.3), [1, 1.3, 1.6, 1.9, 2])
    assert np.allclose(grid.by_count(1e5, 1e7, 3, log=True), [1e5, 1e6, 1e7])
    assert len(grid.product(Km=[1, 2], pk=[1, 2, 3])) == 6
    with pytest.raises(InputError):
        grid.by_step(1, 2, -0.1)


def test_batch_parallel_equals_serial(h2o2):
    tasks = [Task("nozzle", h2o2, (Ratio.km(km), p * 1e6), {"eps": [20, 60]})
             for km in grid.by_count(4.0, 8.0, 5) for p in (3.0, 10.0)]
    tasks.append(Task("equilibrium", h2o2, ("TP", Ratio.km(6.0)), {}))  # ошибка: не задано P и T
    serial = run_batch(tasks, workers=1)
    parallel = run_batch(tasks, workers=2, chunk_size=3)
    assert isinstance(serial[-1], TaskFailure) and isinstance(parallel[-1], TaskFailure)
    for a, b in zip(serial[:-1], parallel[:-1]):
        assert a.converged and b.converged
        assert a.chamber["t"] == b.chamber["t"]
        assert [p["isp_vac"] for p in a.exits()] == [p["isp_vac"] for p in b.exits()]


# --- Обозначения ---------------------------------------------------------

def test_notation_catalog_complete_and_uses_k():
    for q in QUANTITIES.values():
        assert q.name and q.symbol and q.meaning is not None
        assert "γ" not in q.symbol + q.name + q.meaning + q.description
    assert QUANTITIES["k"].symbol == "k"
    assert QUANTITIES["Km"].symbol != QUANTITIES["alpha"].symbol
    assert QUANTITIES["i"].name != QUANTITIES["H"].name
    assert QUANTITIES["pk"].to_display(5e6) == pytest.approx(5.0)   # МПа
