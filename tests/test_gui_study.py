"""Раздел «Параметрические исследования» в интерфейсе."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from astra.projects import AxisSpec  # noqa: E402

from test_gui import app, window  # noqa: E402,F401  (фикстуры)


def run_series(app, window):
    page = window.pages["parametric"]
    window.go_to("parametric")
    page.run()
    page.thread.wait(120000)
    app.processEvents()
    return page


def cells(page, col_title):
    t = page.table
    col = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())].index(col_title)
    return [t.item(r, col).text() for r in range(t.rowCount())]


def test_page_replaces_placeholder_and_runs(app, window):
    page = window.pages["parametric"]
    assert page.rows and page.rows[0].key.currentData() == "alpha"
    page.add_axis()
    assert [r.key.currentData() for r in page.rows] == ["alpha", "pk"]
    assert "42" in page.points_label.text()
    res = run_series(app, window)
    assert res.status.text().startswith("Рассчитано точек: 42"), res.status.text()
    assert res.table.rowCount() == 42 and res.progress.value() == 42
    assert set(cells(res, "Сходимость")) == {"да"}
    assert res.section.currentText().endswith("ε = 75")
    # записано в журнал проекта
    recs = window.state.store.calculations(window.state.project.id)
    assert recs[0].kind == "study" and len(recs[0].results["points"]) == 42


def test_axis_edit_and_section_switch(app, window):
    page = window.pages["parametric"]
    row = page.rows[0]
    row.mode.setCurrentIndex(row.mode.findData("step"))
    row.start.setText("0,7")
    row.stop.setText("0,9")
    row.step.setText("0,1")
    row.step.editingFinished.emit()
    assert window.state.project.study.axes[0] == AxisSpec("alpha", "step", 0.7, 0.9, 0.1, 7, False)
    res = run_series(app, window)
    assert cells(res, "α") == ["0,7", "0,8", "0,9"]
    res.section.setCurrentIndex(0)                  # камера сгорания
    tk = [float(x.replace(",", ".")) for x in cells(res, "T, К")]
    assert tk == sorted(tk) and 3000 < tk[0] < 3600  # Tк растёт к стехиометрии


def test_bad_axis_input_is_reported(app, window):
    page = window.pages["parametric"]
    row = page.rows[0]
    row.start.setText("abc")
    row.start.editingFinished.emit()
    assert "не число" in page.axis_error.text()
    page.run()
    assert "не запущена" in page.status.text()


def test_failed_points_marked_in_table(app, window):
    st_ = window.state
    st_.project.conditions.calc = "HP"
    st_.project.study.axes = [AxisSpec("i", "step", -5e7, 0.0, 2.5e7)]
    st_.set_project(st_.project)
    res = run_series(app, window)
    status = cells(res, "Сходимость")
    assert status[0].startswith("нет") and status[-1] == "да"
    assert cells(res, "T, К")[0] == "—"
    assert "не сошлось" in res.status.text()


def test_shock_has_no_axes(app, window):
    st_ = window.state
    st_.project.conditions.calc = "shock"
    st_.set_project(st_.project)
    page = window.pages["parametric"]
    assert not page.run_btn.isEnabled() and not page.add_axis_btn.isEnabled()
    assert "прямо в исходных условиях" in page.base.text()
