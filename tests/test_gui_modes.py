"""Все постановки расчёта через интерфейс: результат на экране совпадает с ядром."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from astra.core import BAR, q  # noqa: E402
from astra.projects import ComponentSpec  # noqa: E402
from astra.projects.run import run_project  # noqa: E402
from astra.app.widgets import fmt  # noqa: E402

from test_gui import app, run_calc, window  # noqa: E402,F401  (фикстуры)


def set_calc(window, calc):
    page = window.pages["conditions"]
    page.calc.setCurrentIndex(page.calc.findData(calc))
    return page


def table_values(page):
    t = page.values_table
    return {t.item(r, 0).text(): [t.item(r, c).text() for c in range(1, t.columnCount())]
            for r in range(t.rowCount())}


def gaseous_h2_o2(window):
    st = window.state
    st.project.components = [ComponentSpec("H2", "fuel", 100.0, 298.15), ComponentSpec("O2", "oxidizer", 100.0, 298.15)]
    st.project.conditions.ratio_kind, st.project.conditions.ratio_value = "alpha", 1.0
    st.set_project(st.project)


@pytest.mark.parametrize("calc", ["TP", "HP", "SP", "TV", "UV", "SV"])
def test_equilibrium_problems_match_core(app, window, calc):
    page = set_calc(window, calc)
    c = window.state.project.conditions
    c.pk, c.t, c.v = 5e6, 3000.0, 0.1
    if calc[0] == "S":
        c.given_s = 15e3     # Дж/(кг·К): для SP и SV энтропия задаётся всегда
    window.state.set_project(window.state.project)
    if calc[0] == "S":
        assert page.use_given.isChecked() and not page.use_given.isEnabled()
    res = run_calc(app, window)
    assert res.status.text().startswith("Расчёт выполнен"), res.status.text()
    direct = run_project(window.state.project)
    vals = table_values(res)
    for key in ("t", "p", "i", "s", "k", "mu_c"):
        assert vals[q(key).label()][0] == fmt(q(key).to_display(direct[key])), key
    if calc[0] in "HU":
        # состояние по умолчанию — свойство исходных компонентов, и оно сохраняется в результате
        sess_key = {"H": "i", "U": "u"}[calc[0]]
        assert "по исходным компонентам" in res.notes.text()
        assert not page.given[sess_key].isHidden() and page.given[sess_key].edit.isReadOnly()


def test_hp_with_explicit_enthalpy(app, window):
    page = set_calc(window, "HP")
    window.go_to("conditions")
    page.use_given.setChecked(True)
    page.given["i"].edit.setText("-1000")       # кДж/кг
    page.given["i"].edit.editingFinished.emit()
    c = window.state.project.conditions
    assert c.given_i == pytest.approx(-1e6)
    res = run_calc(app, window)
    assert res.status.text().startswith("Расчёт выполнен")
    assert table_values(res)["i, кДж/кг"][0] == "-1000"
    # снятие флажка возвращает значение исходных компонентов
    page.use_given.setChecked(False)
    assert c.given_i is None


def test_rocket_with_explicit_chamber_enthalpy_matches_default(app, window):
    """Задание i камеры, равного энтальпии компонентов, даёт тот же результат, что и расчёт по умолчанию."""
    base = run_project(window.state.project)
    page = window.pages["conditions"]
    window.go_to("conditions")
    page.use_given.setChecked(True)
    page.given["i"].edit.editingFinished.emit()
    assert window.state.project.conditions.given_i is not None
    res = run_project(window.state.project)
    assert res.chamber["t"] == pytest.approx(base.chamber["t"], rel=1e-6)


def test_detonation_in_gui(app, window):
    gaseous_h2_o2(window)
    page = set_calc(window, "detonation")
    window.go_to("conditions")
    assert not page.wave_box.isHidden() and page.nozzle_box.isHidden()
    page.p1.edit.setText("0,1; 2")
    page.p1.edit.editingFinished.emit()
    page.t1.edit.setText("298,15")
    page.t1.edit.editingFinished.emit()
    c = window.state.project.conditions
    assert c.p1 == [pytest.approx(1e5), pytest.approx(2e6)]
    res = run_calc(app, window)
    assert res.status.text().startswith("Расчёт выполнен"), res.status.text()
    vals = table_values(res)
    # RP-1311 №6: D = 2835,53 м/с при 1 бар и 298,15 К
    d = vals["D, м/с"]
    assert d[1] == "2835,53" and d[0] == "—"
    assert res.metrics["D"].text() == "2835,5"


def test_shock_in_gui_needs_gas_and_runs(app, window):
    page = set_calc(window, "shock")
    res = run_calc(app, window)     # пример проекта — жидкие H2(L)/O2(L)
    assert "газообразными" in res.status.text()
    st = window.state
    st.project.components = [ComponentSpec("H2", "mixture", 0.05, 300.0), ComponentSpec("O2", "mixture", 0.05, 300.0),
                             ComponentSpec("Ar", "mixture", 0.90, 300.0)]
    st.project.conditions.basis = "mole"
    c = st.project.conditions
    c.t1, c.p1, c.shock_by, c.u1 = [300.0], [10 * 101325.0 / 760], "u1", [1100.0, 1400.0]
    c.shock_reflected = "equilibrium"
    st.set_project(st.project)
    assert not page.ratio_box.isEnabled()
    res = run_calc(app, window)
    assert res.status.text().startswith("Расчёт выполнен"), res.status.text()
    t = res.values_table
    assert t.columnCount() == 1 + 2 * 3
    vals = table_values(res)
    assert vals["T, К"][1] == "1528,52"        # RP-1311 №7, W₁ = 1100 м/с
    assert vals["T, К"][4] == "2249,06"        # W₁ = 1400 м/с
    assert "Kм" not in "".join(vals)


def test_products_options(app, window):
    page = window.pages["conditions"]
    window.go_to("conditions")
    page.only.edit.setText("H2 O2 H2O OH Unobtainium")
    page.only.edit.editingFinished.emit()
    assert "Unobtainium" in page.error.text()
    page.only.edit.setText("H2 O2 H2O OH H O")
    page.only.edit.editingFinished.emit()
    page.transport.setChecked(True)
    assert page.error.text() == ""
    c = window.state.project.conditions
    assert c.only == ["H2", "O2", "H2O", "OH", "H", "O"] and c.transport
    res = run_calc(app, window)
    assert res.status.text().startswith("Расчёт выполнен"), res.status.text()
    vals = table_values(res)
    assert "η, мкПа·с" in vals and "Pr" in vals
    comp = res.comp_table
    names = {comp.item(r, 0).text() for r in range(comp.rowCount())}
    assert names <= {"H2", "O2", "H2O", "OH", "H", "O"}


def test_finite_area_by_mass_flux(app, window):
    page = window.pages["conditions"]
    window.go_to("conditions")
    page.use_fac.setChecked(True)
    page.fac_by_flux.setChecked(True)
    page.mass_flux.edit.setText("1333,9")
    page.mass_flux.edit.editingFinished.emit()
    c = window.state.project.conditions
    assert c.mass_flux == pytest.approx(1333.9) and c.eps_k is None
    res = run_calc(app, window)
    assert res.status.text().startswith("Расчёт выполнен")
    headers = [res.values_table.horizontalHeaderItem(i).text() for i in range(res.values_table.columnCount())]
    assert headers[1] == "Вход в камеру"
    # RP-1311 №10: T в конце камеры 3341,13 К
    t_end = float(table_values(res)["T, К"][2].replace(",", "."))
    assert t_end == pytest.approx(3341.13, rel=5e-4)


def test_old_project_without_new_fields_loads(app, window, tmp_path):
    from astra.projects import Project
    d = Project.example().to_dict()
    for k in ("given_i", "transport", "only", "t1", "mass_flux"):
        d["conditions"].pop(k)
    d["conditions"]["obsolete"] = 1
    p = Project.from_dict(d)
    assert p.conditions.transport is False and p.conditions.only == []
