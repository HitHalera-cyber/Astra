"""Разделы «Исследование сопла» и «Удельный импульс» в интерфейсе."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from test_gui import app, window  # noqa: E402,F401  (фикстуры)


def headers(t):
    return [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]


def column(t, title):
    col = headers(t).index(title)
    return [t.item(r, col).text() for r in range(t.rowCount())]


def test_nozzle_page_runs(app, window):
    page = window.pages["nozzle"]
    window.go_to("nozzle")
    page.eps_mode.setCurrentIndex(page.eps_mode.findData("list"))
    page.eps_list.edit.setText("5; 25; 100")
    page.eps_list.edited.emit()
    page.pn.edit.setText("0; 0,101325")
    page.pn.edited.emit()
    assert window.state.project.nozzle_study.eps_list == [5, 25, 100]
    assert window.state.project.nozzle_study.pn == pytest.approx([0, 101325])
    page.run()
    page.thread.wait(60000)
    app.processEvents()
    assert page.status.objectName() == "Good", page.status.text()
    assert column(page.table, "ε") == ["5", "25", "100"]
    assert "Iуд(Pн), м/с (равн.)" in headers(page.table)
    assert "ΔIуд(Pн) равн.−замор., м/с" in headers(page.table)
    assert page.pn_view.count() == 2
    assert page.design_table.rowCount() == 2          # Pн = 0,1 МПа × две модели
    assert "Tк =" in page.chamber.text()
    page.pn_view.setCurrentIndex(0)                   # вакуум
    assert set(column(page.table, "Режим истечения")) == {"Истечение в вакуум"}
    assert window.state.last_nozzle is page.result


def test_nozzle_page_bad_input_and_wrong_calc(app, window):
    page = window.pages["nozzle"]
    page.eps_mode.setCurrentIndex(page.eps_mode.findData("list"))
    page.eps_list.edit.setText("0,5")
    page.eps_list.edited.emit()
    assert "больше 1" in page.error.text() or "ε" in page.error.text()
    window.state.project.conditions.calc = "TP"
    window.state.touch()
    assert not page.run_btn.isEnabled()
    assert "недоступно" in page.base.text()


def test_isp_page_runs_and_finds_maximum(app, window):
    page = window.pages["isp"]
    window.go_to("isp")
    page.kind.setCurrentIndex(page.kind.findData("Km"))
    page.start_e.setText("3")
    page.stop_e.setText("8")
    page.count.setValue(11)
    page.eps.edit.setText("50")
    page.pn.edit.setText("0")
    page.models["frozen"].setChecked(True)
    page.find_max.setChecked(True)
    s = window.state.project.isp_study
    assert (s.ratio_kind, s.start, s.stop, s.count, s.eps, s.models) == ("Km", 3, 8, 11, [50], ["equilibrium",
                                                                                              "frozen"])
    page.run()
    page.thread.wait(120000)
    app.processEvents()
    assert page.status.objectName() == "Good", page.status.text()
    assert page.table.rowCount() == 11 and page.progress.value() == 22
    assert set(column(page.table, "Сходимость")) == {"да"}
    assert page.opt_table.rowCount() == 2
    notes = column(page.opt_table, "Примечание")
    assert all(n.startswith("Внутренний") for n in notes)
    window.state.store  # журнал пишется только для сохранённого проекта


def test_isp_page_edge_maximum_warns(app, window):
    page = window.pages["isp"]
    page.kind.setCurrentIndex(page.kind.findData("alpha"))
    page.start_e.setText("0,2")
    page.stop_e.setText("0,35")
    page.count.setValue(4)
    page.eps.edit.setText("50")
    page.pn.edit.setText("0")
    page.run()
    page.thread.wait(120000)
    app.processEvents()
    assert page.status.objectName() == "Warn"
    assert "границе диапазона" in page.status.text()


def test_study_records_go_to_journal(app, window):
    st = window.state
    st.new_project(example=True)
    for key, title in (("nozzle", "Исследование сопла"), ("isp", "Исследование удельного импульса")):
        page = window.pages[key]
        if key == "isp":
            page.count.setValue(5)
        page.run()
        page.thread.wait(120000)
        app.processEvents()
    kinds = [r.kind for r in st.store.calculations(st.project.id)]
    assert {"nozzle_study", "isp_study"} <= set(kinds)
    rec = next(r for r in st.store.calculations(st.project.id) if r.kind == "isp_study")
    assert rec.results["type"] == "isp_study" and rec.results["optima"]
