"""Исследование сопла и удельного импульса: сверка с прямыми вызовами ядра."""

import math

import pytest

from astra.core import CeaSession, InputError, Ratio, classify_regime, isp_at_ambient
from astra.projects import IspStudySpec, NozzleStudySpec, Project
from astra.projects.nozzle import eps_values, ratio_values, run_isp_study, run_nozzle_study


@pytest.fixture
def project():
    return Project.example()      # H2(L)/O2(L), Kм = 5,55157, Pк = 53,3172 бар


def test_eps_values_modes():
    assert eps_values(NozzleStudySpec(eps_mode="list", eps_list=[50, 10, 10])) == [10.0, 50.0]
    vals = eps_values(NozzleStudySpec(eps_mode="count", eps_start=2, eps_stop=200, eps_count=3, eps_log=True))
    assert vals == pytest.approx([2, 20, 200])
    assert eps_values(NozzleStudySpec(eps_mode="step", eps_start=10, eps_stop=30, eps_step=10)) == [10, 20, 30]
    with pytest.raises(InputError):
        eps_values(NozzleStudySpec(eps_mode="list", eps_list=[1.0]))
    with pytest.raises(InputError):
        eps_values(NozzleStudySpec(eps_mode="list", eps_list=[]))


def test_isp_at_ambient_matches_core_at_design(project):
    """В расчётном сечении (Pа = Pн) формула Iуд(Pн) должна дать Iуд ядра (с точностью итераций ядра)."""
    sess = CeaSession(project.propellant())
    res = sess.nozzle(Ratio.km(5.55157), 53.3172e5, pk_p=[10.0, 100.0, 1000.0])
    for p in res.exits():
        assert isp_at_ambient(p["isp_vac"], p["eps"], p["c_star"], 53.3172e5, p["p"]) == pytest.approx(p["isp"],
                                                                                                    rel=1e-6)


def test_nozzle_study_one_chamber_and_matches_core(project):
    spec = NozzleStudySpec(eps_mode="list", eps_list=[5, 25, 100], pn=[0, 101325, 2e4])
    r = run_nozzle_study(project, spec)
    assert r.converged and r.eps == [5, 25, 100] and r.pn == [0, 2e4, 101325]
    eq, fr = r.by_model["equilibrium"], r.by_model["frozen"]
    for k in ("t", "p", "i", "s", "mu"):
        assert eq.chamber[k] == fr.chamber[k]
    sess = CeaSession(project.propellant(), project.products())
    for model in ("equilibrium", "frozen"):
        direct = sess.nozzle(Ratio.km(5.55157), 53.3172e5, eps=[5, 25, 100], model=model)
        got = r.exits(model)
        assert [p["eps"] for p in got] == pytest.approx([5, 25, 100], rel=5e-5)  # допуск итераций ядра по ε
        for a, b in zip(got, [p for p in direct.points if p.kind == "supersonic"]):
            for k in ("t", "p", "isp_vac", "c_star", "w"):
                assert a[k] == pytest.approx(b[k], rel=1e-7)  # другой набор сечений — иной путь итераций
        assert r.isp(model, 0.0) == pytest.approx([p["isp_vac"] for p in got])
        # режим истечения — по соотношению Pа и Pн
        assert r.regimes(model, 101325.0) == [classify_regime(p["p"], 101325.0) for p in got]
    # равновесное расширение даёт больший Iуд.п, чем замороженное
    assert all(a > b for a, b in zip(r.isp("equilibrium", 0), r.isp("frozen", 0)))


def test_nozzle_study_design_sections(project):
    r = run_nozzle_study(project, NozzleStudySpec(eps_mode="list", eps_list=[10, 50], pn=[0, 101325, 2e4]))
    for model in r.by_model:
        assert set(r.design[model]) == {2e4, 101325}
        for pn, pt in r.design[model].items():
            assert pt["p"] == pytest.approx(pn, rel=1e-6)
            assert pt["isp"] == pytest.approx(isp_at_ambient(pt["isp_vac"], pt["eps"], pt["c_star"], r.pk, pn),
                                              rel=1e-6)
        # чем ниже Pн, тем больше расчётная ε
        assert r.design[model][2e4]["eps"] > r.design[model][101325]["eps"]


def test_nozzle_study_rejects_wrong_setup(project):
    project.conditions.calc = "HP"
    with pytest.raises(InputError, match="Камера сгорания и сопло"):
        run_nozzle_study(project)
    project.conditions.calc = "rocket"
    with pytest.raises(InputError):
        run_nozzle_study(project, NozzleStudySpec(models=[]))
    with pytest.raises(InputError):
        run_nozzle_study(project, NozzleStudySpec(pn=[-1.0]))


def test_ratio_values():
    assert ratio_values(IspStudySpec(ratio_kind="Km", mode="step", start=3, stop=5, step=1)) == [3, 4, 5]
    with pytest.raises(InputError):
        ratio_values(IspStudySpec(ratio_kind="alpha", mode="count", start=0, stop=1, count=3))


def test_isp_study_grid_matches_core(project):
    spec = IspStudySpec(ratio_kind="Km", mode="count", start=3, stop=8, count=6, eps=[25, 50], pn=[0, 101325],
                        models=["equilibrium", "frozen"], find_max=False)
    r = run_isp_study(project, spec)
    assert r.n_failed == 0 and not r.optima and len(r.curves()) == 8
    sess = CeaSession(project.propellant(), project.products())
    for curve in r.curves():
        vals = r.isp(curve)
        for km, v in zip(r.ratios, vals):
            d = sess.nozzle(Ratio.km(km), project.conditions.pk, eps=[curve.eps], model=curve.model).exits()[-1]
            assert v == pytest.approx(isp_at_ambient(d["isp_vac"], d["eps"], d["c_star"], r.pk, curve.pn), rel=1e-12)


def test_isp_study_maximum_refined_by_core(project):
    spec = IspStudySpec(ratio_kind="Km", mode="count", start=3, stop=8, count=11, eps=[50], pn=[0],
                        models=["equilibrium"], find_max=True)
    r = run_isp_study(project, spec)
    (opt,) = r.optima
    assert opt.note.startswith("Внутренний")
    grid = r.isp(opt.curve)
    assert opt.isp >= max(grid)
    assert opt.alpha == pytest.approx(opt.km / r.km0)
    sess = CeaSession(project.propellant(), project.products())

    def isp(km):
        return sess.nozzle(Ratio.km(km), r.pk, eps=[50]).exits()[-1]["isp_vac"]
    assert isp(opt.km) == pytest.approx(opt.isp, rel=1e-12)
    for dk in (-0.01, 0.01):
        assert isp(opt.km + dk) <= opt.isp
    assert math.isclose(opt.tk, sess.nozzle(Ratio.km(opt.km), r.pk, eps=[50]).chamber["t"], rel_tol=1e-12)


def test_isp_study_maximum_at_range_edge(project):
    spec = IspStudySpec(ratio_kind="alpha", mode="count", start=0.2, stop=0.35, count=4, eps=[50], pn=[0])
    (opt,) = run_isp_study(project, spec).optima
    assert opt.note.startswith("Наибольшее значение на верхней границе")
    assert opt.ratio == pytest.approx(0.35)


def test_isp_study_cancel(project):
    spec = IspStudySpec(ratio_kind="alpha", count=20, eps=[50])
    r = run_isp_study(project, spec, cancelled=lambda: True)
    assert r.cancelled and not r.optima and r.n_failed == 20


def test_specs_persist(project, tmp_path):
    from astra.projects import ProjectStore
    project.nozzle_study = NozzleStudySpec(eps_mode="list", eps_list=[7.0], pn=[0.0])
    project.isp_study = IspStudySpec(ratio_kind="Km", eps=[30.0], models=["frozen"], freeze_at="chamber")
    store = ProjectStore(tmp_path / "p.sqlite")
    loaded = store.load(store.save(project).id)
    assert loaded.nozzle_study == project.nozzle_study and loaded.isp_study == project.isp_study
    d = project.to_dict()
    d["isp_study"]["unknown_future_key"] = 1
    assert Project.from_dict(d).isp_study == project.isp_study
