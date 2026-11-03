"""Проверка интерфейса без экрана (QT_QPA_PLATFORM=offscreen)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QSettings  # noqa: E402

from astra.core import species_db  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("ini")))
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture()
def window(app, tmp_path):
    from astra.app.main import create_window
    w = create_window(tmp_path / "projects.sqlite")
    w.show()
    yield w
    w.close()


def run_calc(app, w):
    page = w.pages["thermo"]
    page.run()
    page.thread.wait(60000)
    app.processEvents()
    return page


def test_all_twelve_sections_present(window):
    names = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert names == ["Главная", "Топливо и окислитель", "Исходные условия", "Термодинамический расчёт",
                     "Параметрические исследования", "Исследование сопла", "Удельный импульс", "Графики",
                     "Таблицы результатов", "База веществ", "Проекты", "Настройки"]
    for i in range(window.nav.count()):
        window.nav.setCurrentRow(i)


def test_example_calculation_matches_core(app, window):
    page = run_calc(app, window)
    assert page.status.text().startswith("Расчёт выполнен")
    assert page.metrics["tk"].text() == "3383,8"           # RP-1311 №8: 3383,84 К
    t = page.values_table
    headers = [t.horizontalHeaderItem(i).text() for i in range(t.columnCount())]
    assert headers[1] == "Камера сгорания" and headers[-1].endswith("ε = 75")
    rows = {t.item(r, 0).text(): r for r in range(t.rowCount())}
    assert "k" in rows and "γ" not in "".join(rows)
    assert t.item(rows["Iуд.п, м/с"], t.columnCount() - 1).text() == "4554,91"
    assert window.pages["projects"].log.rowCount() == 1   # расчёт записан в журнал


def test_conditions_alpha_recomputes_km(app, window):
    page = window.pages["conditions"]
    window.go_to("conditions")
    page.by_alpha.setChecked(True)
    page.alpha.edit.setText("1")
    page.alpha.edit.editingFinished.emit()
    c = window.state.project.conditions
    assert c.ratio_kind == "alpha" and c.ratio_value == 1.0
    assert page.km.edit.text() == "7,9366827"
    page.pk.edit.setText("abc")
    page.pk.edit.editingFinished.emit()
    assert page.pk.edit.property("invalid") is True
    assert "не число" in page.error.text()


def test_add_species_from_database_and_invalid_temperature(app, window):
    prop = window.pages["propellant"]
    prop.add_species("CH4", "fuel")
    assert window.state.project.components[-1].name == "CH4"
    assert window.state.project.components[-1].t0 == 298.15
    # H2(L) при 298 К вне данных базы — расчёт должен сообщить об этом, а не считать
    window.state.project.components = [c for c in window.state.project.components if c.name != "CH4"]
    window.state.project.components[0].t0 = 298.15
    page = run_calc(app, window)
    assert "вне диапазона" in page.status.text()


def test_projects_new_duplicate(app, window):
    st = window.state
    first = st.project.id
    st.new_project()
    assert st.project.id != first and st.project.components == []
    st.store.duplicate(first, "Копия")
    window.pages["projects"].refresh()
    assert window.pages["projects"].list.rowCount() == 3


def test_theme_switch(app, window):
    window.apply_theme("light")
    assert "#eef0f3" in app.styleSheet()
    window.apply_theme("dark")
    assert "#1b1e23" in app.styleSheet()
