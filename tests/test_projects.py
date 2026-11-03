import math

import pytest

from astra.projects import ComponentSpec, Project, ProjectStore
from astra.projects.run import run_project


@pytest.fixture()
def store(tmp_path):
    s = ProjectStore(tmp_path / "p.sqlite")
    yield s
    s.close()


def test_save_load_roundtrip(store):
    p = Project.example()
    p.conditions.pn = None
    p.conditions.eps = [3.0, 30.0]
    store.save(p)
    q = store.load(p.id)
    assert q.name == p.name and q.components == p.components and q.conditions == p.conditions


def test_list_duplicate_delete(store):
    a = store.save(Project(name="А"))
    b = store.duplicate(a.id)
    assert b.id != a.id and b.name == "А (копия)"
    assert {r[1] for r in store.list()} == {"А", "А (копия)"}
    store.delete(a.id)
    assert [r[0] for r in store.list()] == [b.id]


def test_calculation_log_keeps_inputs_and_results(store):
    p = store.save(Project.example())
    res = run_project(p)
    assert res.converged
    store.log_calculation(p.id, p.conditions.calc, p.to_dict(), res, "3.3.4")
    rec = store.calculations(p.id)[0]
    assert rec.converged and rec.core_version == "3.3.4"
    assert rec.inputs["conditions"]["pk"] == p.conditions.pk
    ch = rec.results["points"][0]
    assert ch["kind"] == "chamber"
    assert ch["values"]["t"] == pytest.approx(res.chamber["t"])
    assert ch["values"].get("eps") is None   # невычисленные величины не подменяются числами
    store.delete(p.id)
    assert store.calculations(p.id) == []


def test_run_equilibrium_problem(store):
    p = Project.example()
    p.conditions.calc = "TP"
    p.conditions.t = 3000.0
    p.conditions.pk = 1e6
    r = run_project(p)
    assert r.converged and r["t"] == pytest.approx(3000.0) and r["p"] == pytest.approx(1e6)
