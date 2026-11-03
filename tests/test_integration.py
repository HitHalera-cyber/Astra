"""Сквозные проверки: сохранение всех исходных данных, параллельные расчёты, повторяемость."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import math

import pytest

from astra.projects import (AxisSpec, ComponentSpec, Conditions, IspStudySpec, NozzleStudySpec, Project,
                            ProjectStore, StudySpec)
from astra.projects import datasets as D
from astra.projects.nozzle import run_isp_study, run_nozzle_study
from astra.projects.run import run_project
from astra.projects.study import run_study


def full_project() -> Project:
    """Проект, в котором ни одно поле не равно значению по умолчанию."""
    return Project(
        name="Полный проект", description="все поля",
        components=[ComponentSpec("CH4(L)", "fuel", 60.0, 111.6), ComponentSpec("H2(L)", "fuel", 40.0, 20.27),
                    ComponentSpec("O2(L)", "oxidizer", 100.0, 90.17)],
        conditions=Conditions(
            basis="mole", ratio_kind="Km", ratio_value=3.1, calc="rocket", pk=7.5e6, t=3100.0, v=0.7,
            given_i=-1.2e6, given_u=-2e6, given_s=1.1e4, chamber_by_tk=False, eps=[5.0, 40.0], eps_sub=[2.0],
            pk_p=[3.0], model="frozen", freeze_at="chamber", pn=5e4, mdot=12.0, eps_k=None, mass_flux=None,
            t1=[300.0], p1=[2e5], shock_by="mach1", u1=[900.0], mach1=[3.0], shock_incident="frozen",
            shock_reflected="equilibrium", det_frozen=True, ions=True, transport=True, only=[], omit=["CH4"],
            insert=[], trace=1e-10),
        study=StudySpec(axes=[AxisSpec("pk", "count", 1e6, 1e7, 1e6, 4, log=True)], workers=2, section=1),
        nozzle_study=NozzleStudySpec(eps_mode="step", eps_start=3.0, eps_stop=30.0, eps_step=3.0, eps_count=8, eps_log=False,
                                     eps_list=[7.0], models=["frozen"],
                                     freeze_at="chamber", pn=[0.0, 2e4]),
        isp_study=IspStudySpec(ratio_kind="Km", mode="step", start=2.0, stop=4.0, step=0.5, count=9, eps=[30.0], pn=[1e4],
                               models=["frozen"], freeze_at="chamber", find_max=False),
    )


def test_every_field_survives_save_and_load(tmp_path):
    store = ProjectStore(tmp_path / "p.sqlite")
    p = full_project()
    defaults = Project()
    for section in ("conditions", "study", "nozzle_study", "isp_study"):
        a, b = asdict(getattr(p, section)), asdict(getattr(defaults, section))
        same = [k for k in a if a[k] == b[k] and k not in ("calc", "chamber_by_tk", "eps_k", "mass_flux", "only", "insert")]
        assert not same, f"{section}: поля по умолчанию {same}"
    loaded = store.load(store.save(p).id)
    assert loaded.to_dict() == p.to_dict()


def test_old_project_without_new_sections_opens():
    d = Project.example().to_dict()
    for k in ("study", "nozzle_study", "isp_study"):
        d.pop(k)
    d["conditions"].pop("transport")
    p = Project.from_dict(d)
    assert p.isp_study == IspStudySpec() and p.conditions.transport is False


def test_results_are_repeatable():
    p = Project.example()
    a, b = run_project(p), run_project(p)
    assert D.from_result(a).rows == D.from_result(b).rows


def test_concurrent_studies_match_sequential():
    """Параллельные потоки (как разделы интерфейса) не мешают друг другу: ядро под общей блокировкой."""
    p = Project.example()
    p.study = StudySpec(axes=[AxisSpec("alpha", "count", 0.6, 1.0, 0.1, 5)])
    noz = NozzleStudySpec(eps_mode="list", eps_list=[10, 50], pn=[0, 101325])
    isp = IspStudySpec(ratio_kind="Km", start=4, stop=7, count=6, eps=[50], find_max=True)
    seq = (D.from_study(run_study(p, workers=1)).rows, D.from_nozzle_study(run_nozzle_study(p, noz)).rows,
           D.from_isp_optima(run_isp_study(p, isp)).rows)
    with ThreadPoolExecutor(3) as ex:
        f1 = ex.submit(lambda: D.from_study(run_study(p, workers=1)).rows)
        f2 = ex.submit(lambda: D.from_nozzle_study(run_nozzle_study(p, noz)).rows)
        f3 = ex.submit(lambda: D.from_isp_optima(run_isp_study(p, isp)).rows)
        par = (f1.result(), f2.result(), f3.result())

    def same(x, y):
        return all(a == b or (isinstance(a, float) and math.isnan(a) and math.isnan(b))
                   for ra, rb in zip(x, y) for a, b in zip(ra, rb)) and len(x) == len(y)
    for s, q_ in zip(seq, par):
        assert same(s, q_)


def test_parallel_processes_match_single_process():
    p = Project.example()
    p.study = StudySpec(axes=[AxisSpec("alpha", "count", 0.6, 1.0, 0.1, 4), AxisSpec("pk", "count", 2e6, 8e6, 1e6, 3)])
    one = D.from_study(run_study(p, workers=1)).rows
    two = D.from_study(run_study(p, workers=2)).rows
    assert one == two
