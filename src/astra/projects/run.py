"""Запуск расчёта проекта через ядро (без интерфейса)."""

from __future__ import annotations

from astra.core import CeaSession, EquilibriumResult, InputError, NozzleResult, WaveResult

from .model import Project


def run_project(project: Project) -> EquilibriumResult | NozzleResult | WaveResult:
    c = project.conditions
    sess = CeaSession(project.propellant(), project.products())
    ratio = None if sess.is_mixture else c.ratio()
    if c.calc == "rocket":
        return sess.nozzle(
            ratio, c.pk, eps=c.eps, pk_p=c.pk_p, eps_sub=c.eps_sub, model=c.model, freeze_at=c.freeze_at,
            tk=c.t if c.chamber_by_tk else None, i=None if c.chamber_by_tk else c.given_i,
            eps_k=c.eps_k, mass_flux=c.mass_flux, pn=c.pn, mdot=c.mdot,
        )
    if c.calc == "shock":
        if len(c.t1) != 1 or len(c.p1) != 1:
            raise InputError("Для ударной волны задаются одно значение T₁ и одно значение P₁; "
                             "серия задаётся скоростями W₁ или числами Маха M₁.")
        series = {"u1": c.u1} if c.shock_by == "u1" else {"mach1": c.mach1}
        return sess.shock(ratio, c.t1[0], c.p1[0], incident=c.shock_incident, reflected=c.shock_reflected,
                          **series)
    if c.calc == "detonation":
        return sess.detonation(ratio, c.t1, c.p1, frozen=c.det_frozen)
    kw = {}
    if c.calc[0] == "T":
        kw["t"] = c.t
    else:
        key = {"H": "i", "U": "u", "S": "s"}[c.calc[0]]
        kw[key] = {"i": c.given_i, "u": c.given_u, "s": c.given_s}[key]
    kw["p" if c.calc[1] == "P" else "v"] = c.pk if c.calc[1] == "P" else c.v
    return sess.equilibrium(c.calc, ratio, **kw)
