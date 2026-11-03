"""Запуск расчёта проекта через ядро (без интерфейса)."""

from __future__ import annotations

from astra.core import CeaSession, EquilibriumResult, NozzleResult

from .model import Project


def run_project(project: Project) -> EquilibriumResult | NozzleResult:
    c = project.conditions
    sess = CeaSession(project.propellant(), project.products())
    if c.calc == "rocket":
        return sess.nozzle(
            c.ratio(), c.pk, eps=c.eps, pk_p=c.pk_p, model=c.model, freeze_at=c.freeze_at,
            tk=c.t if c.chamber_by_tk else None, eps_k=c.eps_k, pn=c.pn, mdot=c.mdot,
        )
    kw = {}
    if c.calc[0] == "T":
        kw["t"] = c.t
    kw["p" if c.calc[1] == "P" else "v"] = c.pk if c.calc[1] == "P" else c.v
    return sess.equilibrium(c.calc, c.ratio(), **kw)
