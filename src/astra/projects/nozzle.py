"""Исследование сопла и удельного импульса.

Исследование сопла: состояние камеры фиксировано (Kм или α, Pк и задание камеры
берутся из исходных условий проекта), меняется только степень расширения ε.
Для каждой химической модели течения — равновесной и замороженной — выполняется
один вызов ядра со всем списком ε, поэтому камера во всех сечениях одна и та же.
Режим истечения (недорасширение, перерасширение, расчётный, вакуум) определяется
отдельно от химической модели, по соотношению Pа и Pн.

Удельный импульс: зависимости Iуд от Kм или α при нескольких ε, Pн и моделях.
Максимум Iуд по соотношению компонентов ищется уточнением по самому ядру
(метод золотого сечения в окрестности лучшей точки сетки); интерполяции между
рассчитанными точками нет.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import math
from typing import Any, Callable

from astra.core import CeaSession, InputError, Ratio, classify_regime, isp_at_ambient, q
from astra.core import grid
from astra.core.batch import CANCELLED, Task, TaskFailure, run_batch
from astra.core.results import NozzleResult, StatePoint

from .model import Conditions, IspStudySpec, NozzleStudySpec, Project
from .run import core_call

MODELS = ("equilibrium", "frozen")
GOLDEN = (math.sqrt(5.0) - 1.0) / 2.0


def _check_rocket(project: Project) -> None:
    if project.conditions.calc != "rocket":
        raise InputError("Исследование сопла и удельного импульса выполняется для постановки «Камера сгорания и "
                         "сопло» (раздел «Исходные условия»).")
    if project.propellant().is_mixture:
        raise InputError("Для исследования сопла нужны горючее и окислитель (соотношение компонентов Kм или α).")


def _values(mode: str, start: float, stop: float, step: float, count: int, log: bool, key: str) -> list[float]:
    if mode == "fixed":
        vals = grid.fixed(start)
    elif mode == "step":
        vals = grid.by_step(start, stop, step)
    else:
        vals = grid.by_count(start, stop, int(count), log=log)
    qt = q(key)
    for v in vals:
        qt.check(float(v))
    return [float(v) for v in vals]


# ====================================================================== сопло
def eps_values(spec: NozzleStudySpec) -> list[float]:
    if spec.eps_mode == "list":
        vals = sorted(set(float(v) for v in spec.eps_list))
        for v in vals:
            q("eps").check(v)
        if not vals:
            raise InputError("Не задано ни одной степени расширения ε.")
    else:
        vals = _values(spec.eps_mode, spec.eps_start, spec.eps_stop, spec.eps_step, spec.eps_count,
                       spec.eps_log, "eps")
    for v in vals:
        if not v > 1.0:
            raise InputError(f"Степень расширения ε = {v:g} должна быть больше 1.")
    return vals


@dataclass
class NozzleStudyResult:
    """Результаты по моделям течения: одна камера, все ε и расчётные сечения Pа = Pн."""

    eps: list[float]
    pn: list[float]
    pk: float
    by_model: dict[str, NozzleResult]
    design: dict[str, dict[float, StatePoint]]   # модель → Pн → сечение с Pа = Pн (ядро, Pк/P = Pк/Pн)

    def exits(self, model: str) -> list[StatePoint]:
        r = self.by_model[model]
        return [p for p in r.points if p.kind == "supersonic"]

    def isp(self, model: str, pn: float) -> list[float]:
        return [isp_at_ambient(p["isp_vac"], p["eps"], p["c_star"], self.pk, pn) for p in self.exits(model)]

    def regimes(self, model: str, pn: float) -> list[str]:
        return [classify_regime(p["p"], pn) for p in self.exits(model)]

    @property
    def chamber(self) -> StatePoint:
        return next(iter(self.by_model.values())).chamber

    @property
    def converged(self) -> bool:
        return all(r.converged for r in self.by_model.values())

    @property
    def message(self) -> str:
        bad = [m for m, r in self.by_model.items() if not r.converged]
        if not bad:
            return "Расчёт выполнен."
        return "; ".join(f"{q_model(m)}: {self.by_model[m].message}" for m in bad)


def q_model(model: str) -> str:
    from astra.core import CHEMICAL_MODELS
    return CHEMICAL_MODELS[model]


def run_nozzle_study(project: Project, spec: NozzleStudySpec | None = None) -> NozzleStudyResult:
    spec = spec or project.nozzle_study
    _check_rocket(project)
    eps = eps_values(spec)
    if not spec.models:
        raise InputError("Выберите хотя бы одну модель течения.")
    for pn in spec.pn:
        if pn < 0:
            raise InputError("Давление окружающей среды Pн не может быть отрицательным.")
    pn_list = sorted(set(float(p) for p in spec.pn))
    c = copy.deepcopy(project.conditions)
    sess = CeaSession(project.propellant(), project.products())
    pk = c.pk
    # Расчётное сечение для каждого Pн > 0 получает ядро напрямую: Pк/P = Pк/Pн.
    design_pkp = [pk / p for p in pn_list if p > 0 and pk / p > 1.0]
    by_model: dict[str, NozzleResult] = {}
    design: dict[str, dict[float, StatePoint]] = {}
    for model in spec.models:
        if model not in MODELS:
            raise InputError(f"Неизвестная модель течения: {model}.")
        c.model, c.freeze_at = model, spec.freeze_at
        c.eps, c.pk_p, c.eps_sub, c.pn = eps, design_pkp, [], None
        method, args, kwargs = core_call(c, False)
        res = sess.nozzle(*args, **kwargs)
        by_model[model] = res
        pr = [p for p in res.points if p.kind == "pressure_ratio"]
        design[model] = {pk / p.target: p for p in pr if p.target}
    return NozzleStudyResult(eps, pn_list, pk, by_model, design)


# ======================================================================== Iуд
def ratio_values(spec: IspStudySpec) -> list[float]:
    vals = _values(spec.mode, spec.start, spec.stop, spec.step, spec.count, False, spec.ratio_kind)
    for v in vals:
        if not v > 0:
            raise InputError(f"{q(spec.ratio_kind).symbol} должно быть положительным: {v:g}.")
    return vals


@dataclass(frozen=True)
class Curve:
    model: str
    eps: float
    pn: float

    @property
    def label(self) -> str:
        pn = "пустота" if self.pn == 0 else f"Pн = {self.pn * 1e-6:g} МПа"
        model = "равн." if self.model == "equilibrium" else "замор."
        return f"ε = {self.eps:g}, {pn}, {model}"


@dataclass
class Optimum:
    curve: Curve
    ratio_kind: str
    ratio: float | None            # Kм или α максимума (None — не найден)
    km: float | None
    alpha: float | None
    isp: float | None
    tk: float | None
    evaluations: int
    note: str                      # пояснение: внутренний максимум, граница диапазона, несходимость


@dataclass
class IspStudyResult:
    ratio_kind: str
    ratios: list[float]
    eps: list[float]
    pn: list[float]
    models: list[str]
    pk: float
    results: dict[str, list[NozzleResult | TaskFailure]]   # модель → по точкам сетки
    optima: list[Optimum] = field(default_factory=list)
    cancelled: bool = False
    km0: float = math.nan

    def curves(self) -> list[Curve]:
        return [Curve(m, e, p) for m in self.models for e in self.eps for p in self.pn]

    def _exit(self, res, eps: float) -> StatePoint | None:
        if isinstance(res, TaskFailure) or not res.converged:
            return None
        for p in res.points:
            if p.kind == "supersonic" and p.target is not None and math.isclose(p.target, eps, rel_tol=1e-12):
                return p
        return None

    def isp(self, curve: Curve) -> list[float]:
        out = []
        for res in self.results[curve.model]:
            p = self._exit(res, curve.eps)
            out.append(isp_at_ambient(p["isp_vac"], p["eps"], p["c_star"], self.pk, curve.pn) if p else math.nan)
        return out

    def chamber_t(self, model: str) -> list[float]:
        out = []
        for res in self.results[model]:
            ok = not isinstance(res, TaskFailure) and res.converged
            out.append(res.chamber["t"] if ok else math.nan)
        return out

    def failed(self, model: str, n: int) -> str | None:
        res = self.results[model][n]
        if isinstance(res, TaskFailure):
            return res.message
        return None if res.converged else res.message

    @property
    def n_failed(self) -> int:
        return sum(self.failed(m, n) is not None for m in self.models for n in range(len(self.ratios)))

    def summary(self) -> str:
        text = f"Рассчитано точек: {len(self.ratios) * len(self.models)} (по {len(self.eps)} ε в каждой)"
        if self.n_failed:
            text += f"; не сошлось или не рассчитано: {self.n_failed}"
        if self.cancelled:
            text += "; расчёт прерван пользователем"
        return text + "."


def _ratio(kind: str, value: float) -> Ratio:
    return Ratio(kind, float(value))


def _conditions(project: Project, spec: IspStudySpec, model: str) -> Conditions:
    c = copy.deepcopy(project.conditions)
    c.model, c.freeze_at = model, spec.freeze_at
    c.eps, c.pk_p, c.eps_sub, c.pn, c.mdot = sorted(set(spec.eps)), [], [], None, None
    return c


def run_isp_study(project: Project, spec: IspStudySpec | None = None, *,
                  progress: Callable[[int, int], None] | None = None,
                  cancelled: Callable[[], bool] | None = None, workers: int | None = 1) -> IspStudyResult:
    spec = spec or project.isp_study
    _check_rocket(project)
    if spec.ratio_kind not in ("Km", "alpha"):
        raise InputError("Варьируется Kм или α.")
    if not spec.eps:
        raise InputError("Задайте хотя бы одну степень расширения ε.")
    for e in spec.eps:
        if not e > 1.0:
            raise InputError(f"Степень расширения ε = {e:g} должна быть больше 1.")
    if not spec.pn:
        raise InputError("Задайте хотя бы одно давление окружающей среды Pн (0 — пустота).")
    if any(p < 0 for p in spec.pn):
        raise InputError("Давление окружающей среды Pн не может быть отрицательным.")
    if not spec.models:
        raise InputError("Выберите хотя бы одну модель течения.")
    ratios = ratio_values(spec)
    prop, products = project.propellant(), project.products()
    tasks, index = [], []
    for model in spec.models:
        base = _conditions(project, spec, model)
        for r in ratios:
            c = copy.deepcopy(base)
            c.ratio_kind, c.ratio_value = spec.ratio_kind, r
            method, args, kwargs = core_call(c, False)
            tasks.append(Task(method, prop, args, kwargs, products))
            index.append(model)
    total = len(tasks)
    results_flat = run_batch(tasks, workers=workers, progress=progress, cancelled=cancelled)
    results: dict[str, list] = {m: [] for m in spec.models}
    for model, res in zip(index, results_flat):
        results[model].append(res)
    was_cancelled = any(isinstance(r, TaskFailure) and r.message == CANCELLED for r in results_flat)
    sess = CeaSession(prop, products)
    out = IspStudyResult(spec.ratio_kind, ratios, sorted(set(spec.eps)), sorted(set(spec.pn)), list(spec.models),
                         project.conditions.pk, results, cancelled=was_cancelled, km0=sess.km0)
    if spec.find_max and not was_cancelled:
        for curve in out.curves():
            out.optima.append(_find_max(sess, project, spec, out, curve))
            if progress:
                progress(total, total)
    return out


def _find_max(sess: CeaSession, project: Project, spec: IspStudySpec, res: IspStudyResult, curve: Curve) -> Optimum:
    """Максимум Iуд по соотношению компонентов: лучшая точка сетки и уточнение по ядру."""
    values = res.isp(curve)
    ok = [i for i, v in enumerate(values) if not math.isnan(v)]
    kind = spec.ratio_kind
    if not ok:
        return Optimum(curve, kind, None, None, None, None, None, 0, "Ни одна точка не рассчитана — максимум не найден.")
    k = max(ok, key=lambda i: values[i])
    base = _conditions(project, spec, curve.model)
    base.eps = [curve.eps]
    evaluations = 0

    def f(x: float) -> tuple[float, NozzleResult | None]:
        nonlocal evaluations
        evaluations += 1
        c = copy.deepcopy(base)
        c.ratio_kind, c.ratio_value = kind, x
        _, args, kwargs = core_call(c, False)
        try:
            r = sess.nozzle(*args, **kwargs)
        except InputError:
            return math.nan, None
        if not r.converged:
            return math.nan, r
        p = r.exits()[-1]
        return isp_at_ambient(p["isp_vac"], p["eps"], p["c_star"], res.pk, curve.pn), r

    def optimum(x: float, isp: float, r: NozzleResult | None, note: str) -> Optimum:
        km = sess.km(_ratio(kind, x))
        return Optimum(curve, kind, x, km, sess.alpha(km), isp, r.chamber["t"] if r else None, evaluations, note)

    if k == 0 or k == len(values) - 1 or math.isnan(values[k - 1]) or math.isnan(values[k + 1]):
        x = res.ratios[k]
        isp, r = f(x)
        edge = "нижней" if k == 0 else "верхней" if k == len(values) - 1 else ""
        note = (f"Наибольшее значение на {edge} границе диапазона — внутреннего максимума в диапазоне нет; "
                "расширьте диапазон." if edge else
                "Рядом с лучшей точкой есть несошедшиеся точки — уточнение не выполнялось.")
        return optimum(x, isp, r, note)

    a, b = res.ratios[k - 1], res.ratios[k + 1]
    c_ = b - GOLDEN * (b - a)
    d_ = a + GOLDEN * (b - a)
    fc, rc = f(c_)
    fd, rd = f(d_)
    tol = 1e-6 * max(abs(res.ratios[k]), 1e-12)
    while abs(b - a) > tol and evaluations < 80:
        if math.isnan(fc) or math.isnan(fd):
            return optimum(res.ratios[k], values[k], None,
                           "При уточнении ядро не сошлось — показана лучшая точка сетки.")
        if fc > fd:
            b, d_, fd, rd = d_, c_, fc, rc
            c_ = b - GOLDEN * (b - a)
            fc, rc = f(c_)
        else:
            a, c_, fc, rc = c_, d_, fd, rd
            d_ = a + GOLDEN * (b - a)
            fd, rd = f(d_)
    x, isp, r = (c_, fc, rc) if fc > fd else (d_, fd, rd)
    return optimum(x, isp, r, "Внутренний максимум, уточнён расчётами ядра (золотое сечение).")
