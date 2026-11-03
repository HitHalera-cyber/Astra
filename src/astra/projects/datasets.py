"""Наборы данных для таблиц, графиков и экспорта.

Набор данных — плоская таблица, собранная из результатов ядра без пересчёта:
каждый столбец — величина в СИ (с обозначением и единицей отображения) или текст
(модель течения, режим истечения, сообщение ядра). Несошедшиеся точки остаются
в наборе: их числовые значения — NaN, сообщение ядра — в столбце «Сходимость».
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from astra.core import (CHEMICAL_MODELS, NOZZLE_REGIMES, EquilibriumResult, NozzleResult, QUANTITIES, StatePoint,
                        WaveResult, q)
from astra.core.batch import TaskFailure
from astra.core.notation import EQUILIBRIUM_PROBLEMS, WAVE_PROBLEMS

TEXT, NUMBER = "text", "number"
SPECIES_PREFIX = "x:"


@dataclass(frozen=True)
class Column:
    key: str
    label: str            # «обозначение, единица» для заголовка и оси
    kind: str = NUMBER    # NUMBER — значение в СИ; TEXT — строка
    to_unit: float = 1.0  # множитель СИ → единица отображения
    title: str = ""       # полное название величины (подсказка, отчёт)

    def display(self, value: Any) -> Any:
        if self.kind == TEXT or value is None:
            return value
        return value * self.to_unit


def qcol(key: str) -> Column:
    qt = q(key)
    return Column(key, qt.label(), NUMBER, qt.to_unit, qt.name)


def tcol(key: str, label: str) -> Column:
    return Column(key, label, TEXT, 1.0, label)


def species_col(name: str) -> Column:
    return Column(SPECIES_PREFIX + name, f"x({name})", NUMBER, 1.0, f"Мольная доля {name}")


@dataclass
class Dataset:
    name: str
    columns: list[Column]
    rows: list[list[Any]]            # значения в СИ (числа) или строки
    meta: dict[str, str] = field(default_factory=dict)

    def index(self, key: str) -> int:
        return [c.key for c in self.columns].index(key)

    def column(self, key: str) -> list[Any]:
        i = self.index(key)
        return [r[i] for r in self.rows]

    def display_column(self, key: str) -> list[Any]:
        c = self.columns[self.index(key)]
        return [c.display(v) for v in self.column(key)]

    def numeric(self) -> list[Column]:
        return [c for c in self.columns if c.kind == NUMBER]

    def text(self) -> list[Column]:
        return [c for c in self.columns if c.kind == TEXT]

    def display_rows(self) -> list[list[Any]]:
        return [[c.display(v) for c, v in zip(self.columns, r)] for r in self.rows]


# ------------------------------------------------------------------ точки
POINT_KEYS = ["t", "p", "rho", "v", "i", "H", "u", "s", "g", "cp", "cp_fr", "cv", "cv_fr", "k", "mu", "mu_c", "a",
              "w", "M", "eps", "pk_p", "c_star", "kt", "kt_p", "isp", "isp_vac", "isp_amb", "kt_n", "f_kr", "f_a",
              "thrust", "w_lab", "w_refl", "p_ratio", "t_ratio", "rho_ratio", "mu_ratio", "D", "M_D",
              "eta", "lam", "lam_fr", "pr", "pr_fr", "Km", "alpha"]


def _present(points: list[StatePoint], keys: list[str]) -> list[str]:
    return [k for k in keys if k in QUANTITIES and any(k in p.values and not math.isnan(p.values[k])
                                                       for p in points)]


def _species(points: list[StatePoint], threshold: float = 5e-6) -> list[str]:
    names: dict[str, float] = {}
    for p in points:
        for sp, x in p.mole_fractions.items():
            if x >= threshold:
                names[sp] = max(names.get(sp, 0.0), x)
    return sorted(names, key=lambda s: -names[s])


def _point_label(p: StatePoint) -> str:
    if p.kind in ("supersonic", "subsonic") and p.target is not None:
        return f"{p.kind_name}, ε = {p.target:g}"
    if p.kind == "pressure_ratio" and p.target is not None:
        return f"{p.kind_name}, Pк/P = {p.target:g}"
    return p.kind_name


def from_result(result: EquilibriumResult | NozzleResult | WaveResult, *, species: bool = True) -> Dataset:
    """Таблица точек одного расчёта: камера и сечения сопла, равновесие или точки волны."""
    if isinstance(result, EquilibriumResult):
        points, name = [result.point], f"Равновесие {EQUILIBRIUM_PROBLEMS.get(result.problem, result.problem)}"
        extra = []
        ok, msg = [result.converged], [result.message]
    elif isinstance(result, NozzleResult):
        points, name = list(result.points), f"Камера и сопло ({result.model_name.lower()})"
        extra = [tcol("regime", "Режим истечения")]
        ok, msg = [result.converged] * len(points), [result.message] * len(points)
    else:
        points, name = list(result.points), WAVE_PROBLEMS[result.problem]
        extra = [tcol("case", "Вариант")]
        cases = result.cases or []
        ok = [cases[p.case]["converged"] if p.case is not None and p.case < len(cases) else result.converged
              for p in points]
        msg = [cases[p.case]["message"] if p.case is not None and p.case < len(cases) else result.message
               for p in points]
    keys = _present(points, POINT_KEYS)
    sp = _species(points) if species else []
    cols = [tcol("point", "Точка")] + extra + [qcol(k) for k in keys] + [species_col(s) for s in sp]
    cols.append(tcol("status", "Сходимость"))
    rows = []
    for p, good, m in zip(points, ok, msg):
        row: list[Any] = [_point_label(p)]
        for c in extra:
            if c.key == "regime":
                row.append(p.regime_name or "")
            else:
                row.append("" if p.case is None else str(p.case + 1))
        row += [p[k] if good else math.nan for k in keys]
        row += [p.mole_fractions.get(s, 0.0) if good else math.nan for s in sp]
        row.append("да" if good else f"нет — {m}")
        rows.append(row)
    return Dataset(name, cols, rows, {"Расчёт": name})


# ----------------------------------------------------------------- серии
def from_study(study) -> Dataset:
    """Параметрическое исследование: по строке на точку серии и сечение результата."""
    sections = study.sections or [""]
    multi = len(sections) > 1
    keys: list[str] = []
    for n in range(len(study)):
        st = study.state(n, -1)
        if st is not None:
            keys = _present([study.state(n, j) for j in range(len(sections)) if study.state(n, j)], POINT_KEYS)
            break
    keys = [k for k in keys if k not in study.axes]
    cols = [qcol(k) for k in study.axes]
    if multi:
        cols.append(tcol("section", "Сечение / точка"))
    cols += [qcol(k) for k in keys] + [tcol("status", "Сходимость")]
    rows = []
    for n in range(len(study)):
        ok = study.converged(n)
        for j, sec in enumerate(sections):
            st = study.state(n, j) if ok else None
            row: list[Any] = [study.points[n][k] for k in study.axes]
            if multi:
                row.append(sec)
            row += [st[k] if st is not None else math.nan for k in keys]
            row.append("да" if ok else f"нет — {study.message(n)}")
            rows.append(row)
    return Dataset("Параметрическое исследование", cols, rows,
                   {"Варьируемые величины": ", ".join(q(k).symbol for k in study.axes),
                    "Точек серии": str(len(study))})


def from_nozzle_study(r) -> Dataset:
    """Исследование сопла: строка на модель течения × Pн × ε."""
    keys = ["eps", "p", "t", "rho", "k", "mu", "a", "w", "M", "c_star", "kt", "isp", "isp_vac", "isp_amb"]
    cols = [tcol("model", "Модель течения"), qcol("pn")] + [qcol(k) for k in keys] + \
        [tcol("regime", "Режим истечения"), tcol("status", "Сходимость")]
    rows = []
    for model, res in r.by_model.items():
        exits = r.exits(model)
        for pn in r.pn:
            isp = r.isp(model, pn)
            for n, e in enumerate(r.eps):
                if res.converged and n < len(exits):
                    p = exits[n]
                    vals = [p[k] if k != "isp_amb" else isp[n] for k in keys]
                    regime = NOZZLE_REGIMES[_regime(p["p"], pn)]
                    status = "да"
                else:
                    vals = [e] + [math.nan] * (len(keys) - 1)
                    regime, status = "", f"нет — {res.message}"
                rows.append([CHEMICAL_MODELS[model], pn] + vals + [regime, status])
    return Dataset("Исследование сопла", cols, rows,
                   {"Pк, МПа": f"{r.pk * 1e-6:g}", "Tк, К": f"{r.chamber['t']:.6g}"})


def _regime(pa: float, pn: float) -> str:
    from astra.core import classify_regime
    return classify_regime(pa, pn)


def from_isp_study(r) -> Dataset:
    """Исследование Iуд: строка на модель × ε × Pн × соотношение компонентов."""
    cols = [tcol("model", "Модель течения"), qcol("eps"), qcol("pn"), qcol("Km"), qcol("alpha"), qcol("tk"),
            qcol("isp_amb"), tcol("status", "Сходимость")]
    rows = []
    for curve in r.curves():
        vals = r.isp(curve)
        tk = r.chamber_t(curve.model)
        for n, x in enumerate(r.ratios):
            km = x if r.ratio_kind == "Km" else x * r.km0
            fail = r.failed(curve.model, n)
            rows.append([CHEMICAL_MODELS[curve.model], curve.eps, curve.pn, km, km / r.km0, tk[n], vals[n],
                         "да" if fail is None else f"нет — {fail}"])
    return Dataset("Удельный импульс", cols, rows, {"Варьируется": q(r.ratio_kind).symbol})


def from_isp_optima(r) -> Dataset:
    cols = [tcol("model", "Модель течения"), qcol("eps"), qcol("pn"), qcol("Km"), qcol("alpha"), qcol("isp_amb"),
            qcol("tk"), Column("evaluations", "Расчётов ядра", NUMBER), tcol("note", "Примечание")]
    nan = math.nan
    rows = [[CHEMICAL_MODELS[o.curve.model], o.curve.eps, o.curve.pn,
             nan if o.km is None else o.km, nan if o.alpha is None else o.alpha,
             nan if o.isp is None else o.isp, nan if o.tk is None else o.tk, float(o.evaluations), o.note]
            for o in r.optima]
    return Dataset("Максимумы удельного импульса", cols, rows)


def collect(state) -> dict[str, Dataset]:
    """Все наборы данных, доступные по последним расчётам текущего сеанса."""
    out: dict[str, Dataset] = {}
    if state.last_result is not None:
        out["thermo"] = from_result(state.last_result)
    if state.last_study is not None:
        out["study"] = from_study(state.last_study)
    if state.last_nozzle is not None:
        out["nozzle"] = from_nozzle_study(state.last_nozzle)
    if state.last_isp is not None:
        out["isp"] = from_isp_study(state.last_isp)
        if state.last_isp.optima:
            out["isp_optima"] = from_isp_optima(state.last_isp)
    return out


def is_failure(x) -> bool:
    return isinstance(x, TaskFailure)
