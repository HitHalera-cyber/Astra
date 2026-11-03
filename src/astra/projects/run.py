"""Запуск расчёта проекта через ядро (без интерфейса)."""

from __future__ import annotations

from typing import Any

from astra.core import CeaSession, EquilibriumResult, InputError, NozzleResult, Ratio, WaveResult

from .model import Conditions, Project


def core_call(conditions: Conditions, is_mixture: bool) -> tuple[str, tuple, dict[str, Any]]:
    """Метод CeaSession и его аргументы для исходных условий проекта.

    Возвращает (метод, позиционные аргументы, именованные аргументы); метод —
    "nozzle", "equilibrium", "shock" или "detonation".
    """
    c = conditions
    ratio: Ratio | None = None if is_mixture else c.ratio()
    if c.calc == "rocket":
        return "nozzle", (ratio, c.pk), dict(
            eps=c.eps, pk_p=c.pk_p, eps_sub=c.eps_sub, model=c.model, freeze_at=c.freeze_at,
            tk=c.t if c.chamber_by_tk else None, i=None if c.chamber_by_tk else c.given_i,
            eps_k=c.eps_k, mass_flux=c.mass_flux, pn=c.pn, mdot=c.mdot,
        )
    if c.calc == "shock":
        if len(c.t1) != 1 or len(c.p1) != 1:
            raise InputError("Для ударной волны задаются одно значение T₁ и одно значение P₁; "
                             "серия задаётся скоростями W₁ или числами Маха M₁.")
        series = {"u1": c.u1} if c.shock_by == "u1" else {"mach1": c.mach1}
        return "shock", (ratio, c.t1[0], c.p1[0]), dict(incident=c.shock_incident, reflected=c.shock_reflected,
                                                         **series)
    if c.calc == "detonation":
        return "detonation", (ratio, c.t1, c.p1), dict(frozen=c.det_frozen)
    kw: dict[str, Any] = {}
    if c.calc[0] == "T":
        kw["t"] = c.t
    else:
        key = {"H": "i", "U": "u", "S": "s"}[c.calc[0]]
        kw[key] = {"i": c.given_i, "u": c.given_u, "s": c.given_s}[key]
    kw["p" if c.calc[1] == "P" else "v"] = c.pk if c.calc[1] == "P" else c.v
    return "equilibrium", (c.calc, ratio), kw


def run_project(project: Project) -> EquilibriumResult | NozzleResult | WaveResult:
    sess = CeaSession(project.propellant(), project.products())
    method, args, kwargs = core_call(project.conditions, sess.is_mixture)
    return getattr(sess, method)(*args, **kwargs)
