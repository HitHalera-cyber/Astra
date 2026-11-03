"""Параметрические исследования: сетки, подстановка значений, серии, отказы и отмена."""

import math

import pytest

from astra.core import BAR, InputError
from astra.core.batch import CANCELLED, TaskFailure, Task, run_batch
from astra.projects import AxisSpec, ComponentSpec, Project, StudySpec
from astra.projects.run import run_project
from astra.projects import study as st


def example():
    return Project.example()


def test_available_axes_follow_problem():
    p = example()
    assert st.available_axes(p.conditions, False) == ["Km", "alpha", "pk", "tk", "i"]
    p.conditions.calc = "TV"
    assert st.available_axes(p.conditions, False) == ["Km", "alpha", "v", "t"]
    p.conditions.calc = "SP"
    assert st.available_axes(p.conditions, True) == ["p", "s"]
    p.conditions.calc = "shock"
    assert st.available_axes(p.conditions, True) == []


def test_axis_values_modes():
    assert list(st.axis_values(AxisSpec("alpha", "fixed", 0.8))) == [0.8]
    assert list(st.axis_values(AxisSpec("alpha", "step", 0.5, 0.8, 0.1))) == pytest.approx([0.5, 0.6, 0.7, 0.8])
    v = st.axis_values(AxisSpec("pk", "count", 1e6, 1e8, count=3, log=True))
    assert list(v) == pytest.approx([1e6, 1e7, 1e8])
    with pytest.raises(InputError):
        st.axis_values(AxisSpec("alpha", "step", 0.5, 0.8, 0.0))
    with pytest.raises(InputError):
        st.axis_values(AxisSpec("tk", "fixed", -10.0))


def test_validation_rules():
    p = example()
    with pytest.raises(InputError, match="одно и то же соотношение"):
        st.points(StudySpec([AxisSpec("Km", "fixed", 5.0), AxisSpec("alpha", "fixed", 0.8)]), p.conditions, False)
    with pytest.raises(InputError, match="взаимоисключающие"):
        st.points(StudySpec([AxisSpec("tk", "fixed", 3000.0), AxisSpec("i", "fixed", -1e6)]), p.conditions, False)
    with pytest.raises(InputError, match="нельзя варьировать"):
        st.points(StudySpec([AxisSpec("v", "fixed", 1.0)]), p.conditions, False)
    with pytest.raises(InputError, match="Слишком много"):
        st.points(StudySpec([AxisSpec("alpha", "count", 0.5, 1, count=200),
                             AxisSpec("pk", "count", 1e6, 1e7, count=200)]), p.conditions, False)


def test_series_point_equals_single_calculation():
    """Каждая точка серии — тот же расчёт, что и одиночный с подставленными значениями."""
    p = example()
    spec = StudySpec([AxisSpec("alpha", "count", 0.6, 1.0, count=3), AxisSpec("pk", "fixed", 10e6)])
    res = st.run_study(p, spec, workers=1)
    assert len(res) == 3 and res.n_failed == 0
    assert res.sections[0] == "Камера сгорания" and res.sections[-1].endswith("ε = 75")
    for n, pt in enumerate(res.points):
        single = example()
        single.conditions.ratio_kind, single.conditions.ratio_value = "alpha", pt["alpha"]
        single.conditions.pk = pt["pk"]
        ref = run_project(single)
        assert res.value(n, "t", 0) == pytest.approx(ref.chamber["t"], rel=1e-12)
        assert res.value(n, "isp_vac") == pytest.approx(ref.exits()[-1]["isp_vac"], rel=1e-12)
        assert res.value(n, "alpha") == pt["alpha"]


def test_chamber_temperature_axis_sets_tk_mode():
    p = example()
    res = st.run_study(p, StudySpec([AxisSpec("tk", "step", 2500.0, 3500.0, 500.0)]), workers=1)
    assert [res.value(n, "t", 0) for n in range(3)] == pytest.approx([2500.0, 3000.0, 3500.0], rel=1e-9)


def test_equilibrium_series_and_entropy_axis():
    p = example()
    p.conditions.calc = "TP"
    res = st.run_study(p, StudySpec([AxisSpec("t", "count", 1000.0, 4000.0, count=4),
                                     AxisSpec("p", "fixed", 1 * BAR)]), workers=1)
    assert res.n_failed == 0 and res.sections == ["Равновесное состояние"]
    assert [res.value(n, "t") for n in range(4)] == pytest.approx([1000, 2000, 3000, 4000])
    # SP: заданная энтропия даёт ту же температуру, что и TP с этой энтропией
    s = res.value(2, "s")
    p.conditions.calc = "SP"
    res_s = st.run_study(p, StudySpec([AxisSpec("s", "fixed", s), AxisSpec("p", "fixed", 1 * BAR)]), workers=1)
    assert res_s.value(0, "t") == pytest.approx(3000.0, rel=1e-5)


def test_failed_points_are_kept_and_flagged():
    """Точка, в которой ядро не сошлось (HP с нереально низкой энтальпией), остаётся в серии с пометкой."""
    p = example()
    p.conditions.calc = "HP"
    res = st.run_study(p, StudySpec([AxisSpec("i", "step", -5e7, 0.0, 2.5e7), AxisSpec("p", "fixed", 1e6)]),
                       workers=1)
    assert len(res) == 3
    assert not res.converged(0)
    assert res.converged(2)
    assert math.isnan(res.value(0, "t")) or not res.converged(0)
    assert "сходимости" in res.message(0) or "Ядро" in res.message(0)
    assert "не сошлось" in res.summary()


def test_mixture_project_series():
    p = example()
    p.components = [ComponentSpec("H2", "mixture", 0.5, 300.0), ComponentSpec("O2", "mixture", 0.5, 300.0)]
    p.conditions.calc = "TP"
    res = st.run_study(p, StudySpec([AxisSpec("t", "fixed", 3000.0), AxisSpec("p", "fixed", 1e5)]), workers=1)
    assert res.converged(0) and "Km" not in res.state(0, 0).values


def test_parallel_series_equals_serial():
    p = example()
    spec = StudySpec([AxisSpec("alpha", "count", 0.6, 1.0, count=5)])
    a = st.run_study(p, spec, workers=1)
    b = st.run_study(p, spec, workers=2)
    assert [a.value(n, "isp_vac") for n in range(5)] == [b.value(n, "isp_vac") for n in range(5)]


def test_cancel_marks_remaining_points():
    p = example()
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return calls["n"] > 3

    res = st.run_study(p, StudySpec([AxisSpec("alpha", "count", 0.5, 1.0, count=10)]), workers=1,
                       cancelled=cancelled)
    assert res.cancelled
    assert sum(isinstance(r, TaskFailure) and r.message == CANCELLED for r in res.results) == 7
    assert "прервана" in res.summary()


def test_cancel_in_process_pool():
    from astra.projects.run import core_call
    p = example()
    prop = p.propellant()
    tasks = []
    for k in range(40):
        method, args, kwargs = core_call(st.apply_point(p.conditions, {"alpha": 0.5 + k * 0.01}), False)
        tasks.append(Task(method, prop, args, kwargs))
    res = run_batch(tasks, workers=2, chunk_size=1, cancelled=lambda: True)
    assert len(res) == 40 and all(r is not None for r in res)
    assert any(isinstance(r, TaskFailure) and r.message == CANCELLED for r in res)


def test_study_spec_saved_with_project(tmp_path):
    from astra.projects import ProjectStore
    store = ProjectStore(tmp_path / "p.sqlite")
    p = example()
    p.study = StudySpec([AxisSpec("Km", "step", 4.0, 6.0, 0.5), AxisSpec("pk", "count", 1e6, 1e7, count=4, log=True)],
                        workers=2, section=0)
    store.save(p)
    q_ = store.load(p.id)
    assert q_.study == p.study
    # старый проект без раздела study
    d = p.to_dict()
    d.pop("study")
    assert Project.from_dict(d).study == StudySpec()
