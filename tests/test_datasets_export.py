"""Наборы данных и экспорт: значения берутся из результатов ядра без изменений."""

import csv
import math

import pytest

from astra.projects import IspStudySpec, NozzleStudySpec, Project, StudySpec, AxisSpec
from astra.projects import datasets as D
from astra.projects import export as E
from astra.projects.nozzle import run_isp_study, run_nozzle_study
from astra.projects.run import run_project
from astra.projects.study import run_study


@pytest.fixture(scope="module")
def project():
    return Project.example()


@pytest.fixture(scope="module")
def rocket(project):
    return run_project(project)


def test_result_dataset_matches_points(rocket):
    ds = D.from_result(rocket)
    assert len(ds.rows) == len(rocket.points)
    for row, p in zip(ds.rows, rocket.points):
        for c in ds.numeric():
            v = row[ds.index(c.key)]
            if c.key.startswith(D.SPECIES_PREFIX):
                assert v == p.mole_fractions.get(c.key[2:], 0.0)
            else:
                assert v == p[c.key] or (math.isnan(v) and math.isnan(p[c.key]))
    assert ds.column("status") == ["да"] * len(rocket.points)
    # отображение — в единицах программы (P в МПа)
    assert ds.display_column("p")[0] == pytest.approx(rocket.chamber["p"] * 1e-6)


def test_wave_and_equilibrium_datasets():
    p = Project.example()
    p.conditions.calc = "TP"
    p.conditions.t = 3000.0
    ds = D.from_result(run_project(p))
    assert len(ds.rows) == 1 and ds.column("t") == [3000.0]


def test_study_dataset_keeps_failed_points(project):
    p = Project.example()
    p.study = StudySpec(axes=[AxisSpec("alpha", "count", 0.6, 1.0, 0.1, 3)])
    s = run_study(p, cancelled=lambda: True)
    ds = D.from_study(s)
    assert len(ds.rows) == 3 * len(s.sections or [""])
    assert all(st.startswith("нет") for st in ds.column("status"))
    assert [c.key for c in ds.columns] == ["alpha", "status"]     # величин ядра нет — ничего не придумано
    assert ds.column("alpha")[0] == pytest.approx(0.6)


def test_study_dataset_partial_failure(project):
    p = Project.example()
    p.study = StudySpec(axes=[AxisSpec("alpha", "count", 0.6, 1.0, 0.1, 3)])
    calls = iter([False, True, True, True, True, True])
    s = run_study(p, cancelled=lambda: next(calls, True), workers=1)
    ds = D.from_study(s)
    ok = [r for r in ds.rows if r[-1] == "да"]
    bad = [r for r in ds.rows if r[-1].startswith("нет")]
    assert ok and bad
    assert all(math.isnan(r[ds.index("t")]) for r in bad)
    assert all(not math.isnan(r[ds.index("t")]) for r in ok)


def test_study_dataset_values(project):
    p = Project.example()
    p.study = StudySpec(axes=[AxisSpec("alpha", "count", 0.6, 1.0, 0.1, 3)])
    s = run_study(p)
    ds = D.from_study(s)
    secs = s.sections
    assert len(ds.rows) == 3 * len(secs)
    last = [r for r in ds.rows if r[ds.index("section")] == secs[-1]]
    assert [r[ds.index("isp_vac")] for r in last] == [s.value(n, "isp_vac", -1) for n in range(3)]


def test_nozzle_and_isp_datasets(project):
    n = run_nozzle_study(project, NozzleStudySpec(eps_mode="list", eps_list=[10, 50], pn=[0, 101325]))
    ds = D.from_nozzle_study(n)
    assert len(ds.rows) == 2 * 2 * 2
    eq_atm = [r for r in ds.rows if r[0] == "Равновесное расширение" and r[1] == 101325]
    assert [r[ds.index("isp_amb")] for r in eq_atm] == n.isp("equilibrium", 101325)
    i = run_isp_study(project, IspStudySpec(ratio_kind="Km", start=3, stop=8, count=6, eps=[50], pn=[0]))
    di, do = D.from_isp_study(i), D.from_isp_optima(i)
    assert len(di.rows) == 6 and di.column("isp_amb") == i.isp(i.curves()[0])
    assert do.column("Km") == [i.optima[0].km]


def test_csv_for_russian_excel(rocket, tmp_path):
    ds = D.from_result(rocket)
    path = E.to_csv(ds, tmp_path / "t.csv", columns=["point", "p", "t"])
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")             # BOM для Excel
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    assert rows[0] == ["Точка", "P, МПа", "T, К"]
    assert rows[1][0] == "Камера сгорания"
    assert float(rows[1][1].replace(",", ".")) == pytest.approx(rocket.chamber["p"] * 1e-6, rel=1e-9)
    assert float(rows[1][2].replace(",", ".")) == pytest.approx(rocket.chamber["t"], rel=1e-9)


def test_xlsx_numbers_and_provenance(rocket, tmp_path):
    from openpyxl import load_workbook
    ds = D.from_result(rocket)
    path = E.to_xlsx([ds, ds], tmp_path / "t.xlsx", project_name="Проверка")
    wb = load_workbook(path)
    assert wb.sheetnames[0] == "Сведения" and len(wb.sheetnames) == 3   # одинаковые имена листов различаются
    info = [[c.value for c in r] for r in wb["Сведения"].iter_rows()]
    assert ["Проект", "Проверка"] in info and any(r[0] == "Ядро" and "NASA CEA" in r[1] for r in info if r[1])
    ws = wb[wb.sheetnames[1]]
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    header = next(i for i, r in enumerate(rows) if r[0] == "Точка")
    col = rows[header].index("T, К")
    assert rows[header + 1][col] == pytest.approx(rocket.chamber["t"])
    assert isinstance(rows[header + 1][col], float)


def test_report_html(rocket, project):
    ds = D.from_result(rocket)
    html = E.report_html("Отчёт", [("Параметры", E.transpose(ds))], project_name="П",
                         inputs=E.project_inputs(project))
    assert "NASA CEA" in html and "Apache-2.0" in html
    assert "H2(L) (горючее" in html and "Pк" in html
    assert "Камера сгорания" in html
