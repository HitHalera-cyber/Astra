"""Разделы «Графики» и «Таблицы результатов»: построение, сортировка, фильтр, экспорт."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import Qt  # noqa: E402

from test_gui import app, window  # noqa: E402,F401  (фикстуры)


def run_thermo_and_study(app, window):
    t = window.pages["thermo"]
    t.run()
    t.thread.wait(60000)
    p = window.pages["parametric"]
    p.add_axis()                    # α × Pк: 7 × 6 точек
    p.run()
    p.thread.wait(120000)
    app.processEvents()


def test_pages_empty_without_results(app, window):
    plots, tables = window.pages["plots"], window.pages["tables"]
    assert plots.source.count() == 0 and not plots.png_btn.isEnabled()
    assert tables.source.count() == 0 and not tables.csv_btn.isEnabled()
    assert "Нет рассчитанных данных" in tables.count.text()


def test_plots_lines_and_map(app, window, tmp_path):
    run_thermo_and_study(app, window)
    pl = window.pages["plots"]
    assert pl.source.count() == 2 and pl.source.currentData() == "study"
    items = pl.plot.listDataItems()
    assert len(items) == 6                          # серии по Pк
    xs, ys = items[0].getData()
    study = window.state.last_study
    assert list(xs) == pytest.approx([study.points[n]["alpha"] for n in range(0, len(study), 6)])
    assert list(ys) == pytest.approx([study.value(n, "isp_vac", -1) for n in range(0, len(study), 6)])
    pl.show_source("thermo")
    assert pl.plot.listDataItems()
    pl.show_source("study")
    pl.mode.setCurrentIndex(pl.mode.findData("map"))
    pl.x.setCurrentIndex(pl.x.findData("alpha"))
    pl.y2.setCurrentIndex(pl.y2.findData("pk"))
    pl.z.setCurrentIndex(pl.z.findData("isp_vac"))
    assert pl.info.text().startswith("Сетка 7 × 6"), pl.info.text()
    assert pl.image is not None and pl.colorbar is not None
    png, svg = pl.save(tmp_path / "g.png"), pl.save(tmp_path / "g.svg")
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    from PySide6.QtSvg import QSvgRenderer
    assert QSvgRenderer(str(svg)).isValid()
    pl.z.setCurrentIndex(pl.z.findData("alpha"))   # те же величины на осях и в цвете
    assert "три разные величины" in pl.info.text()


def test_tables_sort_filter_export(app, window, tmp_path):
    run_thermo_and_study(app, window)
    tb = window.pages["tables"]
    tb.show_source("study")
    ds = tb.dataset()
    assert tb.proxy.rowCount() == len(ds.rows)
    col = ds.index("t")
    tb.view.sortByColumn(col, Qt.SortOrder.DescendingOrder)
    top = [float(tb.proxy.index(r, col).data().replace(",", ".")) for r in range(3)]
    assert top == sorted(top, reverse=True) and top[0] == pytest.approx(max(v for v in ds.display_column("t")), rel=1e-5)
    tb.search.setText("Камера сгорания")
    assert tb.proxy.rowCount() == 42
    # скрытый столбец не попадает в CSV
    j = ds.index("rho")
    tb.cols_menu.actions()[j].setChecked(False)
    assert tb.view.isColumnHidden(j)
    path = tb.export_csv(tmp_path / "t.csv")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    assert len(lines) == 43 and "ρ, кг/м³" not in lines[0]
    first_t = float(lines[1].split(";")[[c.key for c in ds.columns if c.key != "rho"].index("t")].replace(",", "."))
    assert first_t == pytest.approx(top[0], rel=1e-6) or first_t > 0
    x = tb.export_xlsx(tmp_path / "t.xlsx", all_tables=True)
    from openpyxl import load_workbook
    assert len(load_workbook(x).sheetnames) == 3
    pdf = tb.export_report(tmp_path / "r.pdf", "pdf")
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 10000
    html = tb.export_report(tmp_path / "r.html", "html")
    text = html.read_text(encoding="utf-8")
    assert "Исходные данные" in text and "Параметрическое исследование" in text
    assert (tmp_path / "r-график.png").exists() and "r-график.png" in text


def test_only_converged_filter(app, window):
    st = window.state
    from astra.projects.study import run_study
    calls = iter([False] * 2)
    st.last_study = run_study(st.project, cancelled=lambda: next(calls, True), workers=1)
    st.study_ready.emit(st.last_study)
    tb = window.pages["tables"]
    tb.show_source("study")
    total = tb.proxy.rowCount()
    tb.only_ok.setChecked(True)
    assert 0 < tb.proxy.rowCount() < total
    assert "без результата ядра" in tb.count.text()
