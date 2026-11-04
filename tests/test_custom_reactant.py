"""Собственные вещества (формула и энтальпия заданы пользователем): задача NASA RP-1311 №5."""

import contextlib
import io
import math
import os
from pathlib import Path
import runpy

import pytest

import cea
from astra.core import (CeaSession, Component, FUEL, InputError, MIXTURE, OXIDIZER, ProductOptions, Propellant,
                        Ratio, parse_formula)
from astra.projects import ComponentSpec, Project
from astra.projects.export import project_inputs

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from test_gui import app, window  # noqa: E402,F401  (фикстуры)

SAMPLE = Path(cea.__file__).parent / "samples" / "rp1311" / "example5.py"
CAL = 4.184
BINDER = dict(formula=(("C", 1.0), ("H", 1.86955), ("O", 0.031256), ("S", 0.008415)),
              enthalpy=-2999.082 * CAL, mw=14.6652984484)


@pytest.fixture(scope="module")
def nasa():
    """Задача №5, рассчитанная образцом NASA (samples/rp1311/example5.py из пакета ядра) без Astra."""
    if not SAMPLE.exists():
        pytest.skip("в пакете ядра нет образца example5.py")
    with contextlib.redirect_stdout(io.StringIO()):
        return runpy.run_path(str(SAMPLE))


def ex5_session(nasa, **binder):
    comps = (Component("NH4CLO4(I)", MIXTURE, 72.06),
             Component("CHOS-Binder", MIXTURE, 18.58, **(binder or BINDER)),
             Component("AL(cr)", MIXTURE, 9.0), Component("MgO(cr)", MIXTURE, 0.2),
             Component("H2O(L)", MIXTURE, 0.16))
    return CeaSession(Propellant(comps), ProductOptions(omit=tuple(nasa["omit_names"])))


def test_example5_matches_nasa_sample(nasa):
    sess = ex5_session(nasa)
    assert sess.reactant_property(math.nan, "i") / 1e3 / CAL == pytest.approx(nasa["enthalpy"][0], rel=1e-9)
    for j, p in enumerate(nasa["pressures"]):
        r = sess.equilibrium("HP", None, p=float(p) * 1e5)
        assert r.converged, r.message
        v = r.point.values
        assert v["t"] == pytest.approx(nasa["T_out"][j], rel=1e-6)
        assert v["k"] == pytest.approx(nasa["gamma_s"][j], rel=1e-6)
        assert v["mu"] == pytest.approx(nasa["molecular_weight_MW"][j], rel=1e-6)
        assert v["cp"] / 1e3 / CAL == pytest.approx(nasa["cp_eq"][j], rel=1e-6)
        assert v["s"] / 1e3 / CAL == pytest.approx(nasa["entropy"][j], rel=1e-6)
        for name in ("H2O", "HCL", "CO", "AL2O3(L)"):
            if name in nasa["mole_fractions"]:
                assert r.point.mole_fractions[name] == pytest.approx(nasa["mole_fractions"][name][j],
                                                                     rel=1e-4, abs=1e-9)


def test_molar_mass_optional_core_computes_it(nasa):
    sess = ex5_session(nasa, formula=BINDER["formula"], enthalpy=BINDER["enthalpy"])
    t = sess.equilibrium("HP", None, p=34.473652e5).point.values["t"]
    assert t == pytest.approx(nasa["T_out"][0], rel=1e-4)


def test_custom_fuel_in_rocket():
    """Собственное горючее с формулой метана даёт тот же результат, что и CH4 из базы."""
    from astra.core import species_db
    ch4 = species_db.by_name("CH4")
    base = CeaSession(Propellant((Component("CH4", FUEL), Component("O2", OXIDIZER))))
    own = CeaSession(Propellant((Component("CH4-own", FUEL, formula=(("C", 1), ("H", 4)),
                                           enthalpy=ch4.hf), Component("O2", OXIDIZER))))
    assert own.km0 == pytest.approx(base.km0, rel=1e-6)
    a = base.nozzle(Ratio.alpha(0.9), 5e6, eps=[20.0])
    b = own.nozzle(Ratio.alpha(0.9), 5e6, eps=[20.0])
    assert b.converged
    assert b.chamber["t"] == pytest.approx(a.chamber["t"], rel=1e-5)
    assert b.points[-1]["isp_vac"] == pytest.approx(a.points[-1]["isp_vac"], rel=1e-5)


@pytest.mark.parametrize("text, want", [
    ("C 1 H 1.86955 O 0.031256 S 0.008415", (("C", 1.0), ("H", 1.86955), ("O", 0.031256), ("S", 0.008415))),
    ("C1 H1,87 O0,03", (("C", 1.0), ("H", 1.87), ("O", 0.03))),
    ("N1H4Cl1O4", (("N", 1.0), ("H", 4.0), ("CL", 1.0), ("O", 4.0))),
    ("Al 2; O 3", (("AL", 2.0), ("O", 3.0))),
])
def test_parse_formula(text, want):
    assert parse_formula(text) == want


@pytest.mark.parametrize("text", ["", "CH4", "Xx 1", "C 1 C 2", "C 1 #"])
def test_parse_formula_rejects(text):
    with pytest.raises(InputError):
        parse_formula(text)


def test_validation():
    with pytest.raises(InputError, match="энтальп"):
        Component("A", FUEL, formula=(("C", 1),))
    with pytest.raises(InputError, match="положительн"):
        Component("A", FUEL, formula=(("C", -1),), enthalpy=0.0)
    with pytest.raises(InputError, match="только для собственного"):
        Component("H2", FUEL, enthalpy=0.0)
    with pytest.raises(InputError, match="совпадает с веществом базы"):
        CeaSession(Propellant((Component("CH4", FUEL, formula=(("C", 1), ("H", 4)), enthalpy=0.0),
                               Component("O2", OXIDIZER))))
    for bad in ("Связка", "TOO-LONG-NAME-1234", "a b"):
        with pytest.raises(InputError, match="латиницей"):
            Component(bad, FUEL, formula=(("C", 1),), enthalpy=0.0)


def test_project_roundtrip_and_report():
    p = Project.example()
    p.components[0] = ComponentSpec("Binder", "fuel", 100.0, 298.15, formula={"C": 1.0, "H": 1.86955},
                                    enthalpy=-12548.0, mw=None)
    q = Project.from_dict(p.to_dict())
    assert q.components[0] == p.components[0]
    assert q.components[0].to_core().is_custom
    old = {"name": "H2(L)", "role": "fuel", "amount": 100.0, "t0": 20.27}   # проект предыдущих версий
    assert not ComponentSpec.from_dict(old).is_custom
    assert "собственное вещество: C 1 H 1.86955, энтальпия -12.548 кДж/моль" in project_inputs(q)["Компоненты"]


def test_gui_custom_dialog(window):
    from astra.app.pages.propellant import CustomReactantDialog
    page = window.pages["propellant"]
    n = len(window.state.project.components)
    dlg = CustomReactantDialog(page, role="fuel")
    dlg.name.setText("CHOS-Binder")
    dlg.formula.setText("C 1 H 1,86955 O 0,031256 S 0,008415")
    assert "S — 0,008415" in dlg.parsed.text()
    dlg.accept()
    assert "энтальпия" in dlg.error.text()          # не задана — окно не закрывается
    dlg.enthalpy.setText("−12,548")
    dlg.accept()
    assert dlg.result() == dlg.DialogCode.Accepted
    page.put_custom(dlg.result_spec)
    comps = window.state.project.components
    assert len(comps) == n + 1 and comps[-1].formula["S"] == 0.008415 and comps[-1].enthalpy == -12548.0
    assert page.table.item(n, 4).text() == "C 1 H 1.86955 O 0.031256 S 0.008415"
    assert "Kм⁰" in page.km0_label.text()

    again = CustomReactantDialog(page, comps[-1], taken=tuple(c.name for c in comps[:-1]))
    again.name.setText("H2(L)")
    again.accept()
    assert "базы NASA CEA" in again.error.text()
    again.name.setText("CHOS-Binder")
    again.mw.setText("14,6652984484")
    again.accept()
    page.put_custom(again.result_spec, n)
    assert window.state.project.components[n].mw == pytest.approx(14.6652984484)
