"""Проверка интерфейса без экрана (QT_QPA_PLATFORM=offscreen)."""

import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QEvent, QSettings  # noqa: E402

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
    # окно удаляется сразу, а не сборщиком мусора при завершении интерпретатора
    page = w.pages.get("thermo")
    if page is not None and page.thread is not None:
        page.thread.wait(60000)
    w.close()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    del w
    gc.collect()


def run_calc(app, w):
    page = w.pages["thermo"]
    page.run()
    page.thread.wait(60000)
    app.processEvents()
    return page


def test_all_twelve_sections_present(window):
    from astra.app.main_window import FULL_NAME_ROLE
    names = [window.nav.item(i).data(FULL_NAME_ROLE) for i in range(window.nav.count())]
    assert names == ["Главная", "Топливо и окислитель", "Исходные условия", "Термодинамический расчёт",
                     "Параметрические исследования", "Исследование сопла", "Удельный импульс", "Графики",
                     "Таблицы результатов", "База веществ", "Проекты", "Настройки"]
    for i in range(window.nav.count()):
        assert window.nav.item(i).toolTip() == names[i]     # полное название — в подсказке
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
    from astra.app.theme import THEMES
    window.apply_theme("light")
    assert THEMES["light"]["bg2"] in app.styleSheet() and window.theme_btn.text() == "Тёмная тема"
    window.toggle_theme()
    assert window.theme == "dark" and THEMES["dark"]["bg2"] in app.styleSheet()
    assert window.pages["settings"].theme.currentData() == "dark"   # список тем в настройках следует за кнопкой


def test_route_and_engine_follow_results(app, window):
    steps = {s["key"]: s for s in window.route_steps()}
    assert steps["propellant"]["done"] and not steps["thermo"]["done"]
    assert steps["thermo"]["sub"] == "не выполнялся"
    page = run_calc(app, window)
    steps = {s["key"]: s for s in window.route_steps()}
    assert steps["thermo"]["done"] and steps["thermo"]["sub"].startswith("Tк 3384")
    st = {s["title"]: s for s in page.engine.stations}
    assert dict((r[0], r[1]) for r in st["КАМЕРА СГОРАНИЯ"]["rows"])["Tк"] == "3384"
    assert page.engine.headline[1] == "4554,9"                  # Iуд.п на последнем сечении, ε = 75
    assert not page.engine.isHidden() and page.cards_box.isHidden()
    window.route.step_clicked.emit("nozzle")
    assert window.current_key() == "nozzle"


def test_qt_binding_keeps_none_refcount(app):
    """Регрессия: PySide6 6.12.0 на Python 3.11 портил счётчик ссылок None в каждом
    вызове void-метода, и программа падала («deallocating None»)."""
    import sys
    label = QtWidgets.QLabel()
    label.setText("x")
    before = sys.getrefcount(None)
    for _ in range(1000):
        label.setText("x")
    assert sys.getrefcount(None) - before > -100
