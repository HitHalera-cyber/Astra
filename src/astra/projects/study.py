"""Параметрические исследования: серии расчётов по сеткам параметров.

Каждая точка серии — отдельный полный расчёт ядром NASA CEA при исходных
условиях проекта, в которых изменены только варьируемые величины. Точки
независимы и выполняются пакетом (`astra.core.batch`) в нескольких процессах.
Несошедшаяся точка или точка с недопустимыми исходными данными остаётся в
серии с флагом и сообщением; её значения не подставляются и не интерполируются.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import math
from typing import Any, Callable

from astra.core import InputError, q
from astra.core import grid
from astra.core.batch import CANCELLED, Result, Task, TaskFailure, run_batch
from astra.core.results import EquilibriumResult, NozzleResult, StatePoint

from .model import AxisSpec, Conditions, Project, StudySpec
from .run import core_call

ROCKET_AXES = ["Km", "alpha", "pk", "tk", "i"]

# название оси для пользователя
AXIS_TITLES = {
    "Km": "Kм — соотношение компонентов",
    "alpha": "α — коэффициент избытка окислителя",
    "pk": "Pк — давление в камере",
    "tk": "Tк — температура в камере (вместо энтальпии)",
    "i": "i — удельная энтальпия",
    "p": "P — давление",
    "t": "T — температура",
    "v": "v — удельный объём",
    "u": "u — удельная внутренняя энергия",
    "s": "S — удельная энтропия",
}

MODES = {"fixed": "фиксированное значение", "step": "от — до с шагом", "count": "от — до, число точек"}

MAX_POINTS = 20000
AUTO_PARALLEL_FROM = 1500   # с какого числа точек серия по умолчанию считается в нескольких процессах


def available_axes(conditions: Conditions, is_mixture: bool) -> list[str]:
    """Величины, которые можно варьировать в текущей постановке."""
    calc = conditions.calc
    ratio = [] if is_mixture else ["Km", "alpha"]
    if calc == "rocket":
        return ratio + ["pk", "tk", "i"]
    if calc in ("shock", "detonation"):
        return []
    out = list(ratio)
    out.append("p" if calc[1] == "P" else "v")
    out.append({"T": "t", "H": "i", "U": "u", "S": "s"}[calc[0]])
    return out


def axis_quantity(key: str):
    return q(key)


def axis_values(axis: AxisSpec):
    if axis.mode == "fixed":
        values = grid.fixed(axis.start)
    elif axis.mode == "step":
        values = grid.by_step(axis.start, axis.stop, axis.step)
    elif axis.mode == "count":
        values = grid.by_count(axis.start, axis.stop, int(axis.count), log=axis.log)
    else:
        raise InputError(f"Неизвестный способ задания значений: {axis.mode}.")
    qt = q(axis.key)
    for v in values:
        qt.check(float(v))
        if axis.key in ("Km", "alpha", "pk", "p", "v") and not v > 0:
            raise InputError(f"{qt.symbol} должно быть положительным: {v:g}.")
    return values


def validate(spec: StudySpec, conditions: Conditions, is_mixture: bool) -> None:
    allowed = available_axes(conditions, is_mixture)
    if not allowed:
        raise InputError("Для ударной волны и детонации серии задаются в исходных условиях "
                         "(несколько W₁, M₁, P₁ или T₁); параметрическое исследование для них не нужно.")
    keys = [a.key for a in spec.axes]
    if not keys:
        raise InputError("Не задано ни одной варьируемой величины.")
    if len(set(keys)) != len(keys):
        raise InputError("Одна и та же величина указана в нескольких осях.")
    for k in keys:
        if k not in allowed:
            raise InputError(f"Величину {q(k).symbol} нельзя варьировать в текущей постановке "
                             f"(доступны: {', '.join(q(a).symbol for a in allowed)}).")
    if "Km" in keys and "alpha" in keys:
        raise InputError("Kм и α задают одно и то же соотношение компонентов — варьируйте одну из них.")
    if "tk" in keys and "i" in keys:
        raise InputError("Tк и i камеры — взаимоисключающие способы задания камеры; варьируйте одну из них.")


def points(spec: StudySpec, conditions: Conditions, is_mixture: bool) -> list[dict[str, float]]:
    validate(spec, conditions, is_mixture)
    axes = {a.key: axis_values(a) for a in spec.axes}
    n = math.prod(len(v) for v in axes.values())
    if n > MAX_POINTS:
        raise InputError(f"Слишком много расчётных точек: {n} (не более {MAX_POINTS}). Уменьшите число значений.")
    return grid.product(**axes)


def apply_point(conditions: Conditions, point: dict[str, float]) -> Conditions:
    """Копия исходных условий с подставленными значениями варьируемых величин."""
    c = copy.deepcopy(conditions)
    for key, value in point.items():
        if key in ("Km", "alpha"):
            c.ratio_kind, c.ratio_value = key, value
        elif key in ("pk", "p"):
            c.pk = value
        elif key == "tk":
            c.chamber_by_tk, c.t = True, value
        elif key == "t":
            c.t = value
        elif key == "v":
            c.v = value
        elif key == "i":
            c.given_i = value
            if c.calc == "rocket":
                c.chamber_by_tk = False
        elif key == "u":
            c.given_u = value
        elif key == "s":
            c.given_s = value
    return c


@dataclass
class StudyResult:
    """Результаты серии: для каждой точки — значения осей и результат ядра (или отказ)."""

    calc: str
    axes: list[str]
    points: list[dict[str, float]]
    results: list[Result]
    cancelled: bool = False
    sections: list[str] = field(default_factory=list)   # подписи точек результата (камера, ε = …)

    def __len__(self) -> int:
        return len(self.points)

    def converged(self, n: int) -> bool:
        r = self.results[n]
        return not isinstance(r, TaskFailure) and bool(r.converged)

    def message(self, n: int) -> str:
        return self.results[n].message

    def state(self, n: int, section: int) -> StatePoint | None:
        r = self.results[n]
        if isinstance(r, TaskFailure):
            return None
        if isinstance(r, EquilibriumResult):
            return r.point
        pts = r.points
        if not pts:
            return None
        idx = section if section >= 0 else len(self.sections) + section
        return pts[idx] if 0 <= idx < len(pts) else None

    def value(self, n: int, key: str, section: int = -1) -> float:
        """Значение величины (СИ) в точке серии n; NaN, если ядро его не вычислило."""
        if key in self.points[n]:
            return self.points[n][key]
        st = self.state(n, section)
        return st[key] if st is not None else math.nan

    @property
    def n_failed(self) -> int:
        return sum(not self.converged(i) for i in range(len(self)))

    def summary(self) -> str:
        bad = self.n_failed
        text = f"Рассчитано точек: {len(self)}"
        if bad:
            text += f"; не сошлось или не рассчитано: {bad}"
        if self.cancelled:
            text += "; серия прервана пользователем"
        return text + "."


def _sections(results: list[Result]) -> list[str]:
    from astra.core.notation import POINT_KINDS
    for r in results:
        if isinstance(r, NozzleResult) and r.converged:
            out = []
            for p in r.points:
                if p.kind in ("supersonic", "subsonic"):
                    out.append(f"{POINT_KINDS[p.kind]}, ε = {p.target:g}")
                elif p.kind == "pressure_ratio":
                    out.append(f"{POINT_KINDS[p.kind]}, Pк/P = {p.target:g}")
                else:
                    out.append(POINT_KINDS[p.kind])
            return out
        if isinstance(r, EquilibriumResult):
            return ["Равновесное состояние"]
    return []


def run_study(project: Project, spec: StudySpec | None = None, *,
              progress: Callable[[int, int], None] | None = None,
              cancelled: Callable[[], bool] | None = None,
              workers: int | None = None) -> StudyResult:
    spec = spec or project.study
    prop = project.propellant()
    is_mixture = prop.is_mixture
    pts = points(spec, project.conditions, is_mixture)
    products = project.products()
    tasks = []
    for pt in pts:
        method, args, kwargs = core_call(apply_point(project.conditions, pt), is_mixture)
        tasks.append(Task(method, prop, args, kwargs, products))
    n_workers = workers if workers is not None else spec.workers
    if n_workers is None:
        # Ядро считает точку за миллисекунды; запуск процессов окупается только на больших сериях.
        n_workers = 1 if len(tasks) < AUTO_PARALLEL_FROM else None
    results = run_batch(tasks, workers=n_workers, progress=progress, cancelled=cancelled)
    was_cancelled = any(isinstance(r, TaskFailure) and r.message == CANCELLED for r in results)
    return StudyResult(project.conditions.calc, [a.key for a in spec.axes], pts, results,
                       cancelled=was_cancelled, sections=_sections(results))
