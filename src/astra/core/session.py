"""Сеанс работы с ядром NASA CEA для одного набора исходных веществ.

Это единственное место Astra, где вызываются функции ядра. Здесь:
- исходные данные проверяются и переводятся в форму, которую ожидает ядро;
- вызываются `cea.EqSolver` и `cea.RocketSolver` (алгоритмы ядра не меняются);
- результаты переводятся в СИ и в ключи отечественной системы обозначений;
- сходимость и коды ошибок ядра передаются в результат без сокрытия.

Дополнительно к выводу ядра вычисляются только величины, которые однозначно
следуют из него точными соотношениями (α, H = i + W²/2, Iуд(Pн), Fкр, тяга).
"""

from __future__ import annotations

import functools
import math
import re
import threading
import warnings
from typing import Any, Iterable, Sequence

import numpy as np

from .errors import CoreError, InputError
from .notation import q
from .propellant import FUEL, OXIDIZER, ProductOptions, Propellant, Ratio
from .results import EquilibriumResult, NozzleResult, StatePoint

import cea as _cea

BAR = 1.0e5          # Па в 1 бар (единица давления ядра)
R_UNIV = float(_cea.R)  # Дж/(кмоль·К), универсальная газовая постоянная ядра

_PROBLEMS = {"TP", "HP", "SP", "TV", "UV", "SV"}


# Ядро хранит базу и рабочие массивы в глобальном состоянии: вызовы из разных потоков
# одного процесса (например, интерфейс и фоновый расчёт) выполняются по очереди.
CORE_LOCK = threading.RLock()


def _locked(method):
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        with CORE_LOCK:
            return method(*args, **kwargs)
    return wrapper


def core_version() -> str:
    return str(_cea.__version__)


def _ensure_init() -> None:
    if not _cea.is_initialized():
        _cea.init()


def _error_name(code: int) -> str:
    if code == int(_cea.SUCCESS):
        return "Расчёт выполнен."
    if code == int(_cea.NOT_CONVERGED):
        return "Ядро NASA CEA не достигло сходимости (CEA_NOT_CONVERGED). Результат недостоверен."
    if code == int(_cea.LAST_VALID_SOLUTION):
        return "Ядро вернуло последнее достоверное решение (CEA_LAST_VALID_SOLUTION)."
    return f"Ядро NASA CEA вернуло код ошибки {code}."


def _call_core(func, *args, **kwargs) -> list[str]:
    """Вызов ядра с перехватом предупреждений привязки (они попадают в результат)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            func(*args, **kwargs)
        except RuntimeError as exc:
            raise CoreError(f"Ошибка ядра NASA CEA: {exc}") from exc
        except ValueError as exc:
            raise InputError(f"Ядро NASA CEA отклонило исходные данные: {exc}") from exc
    return [str(w.message) for w in caught]


def _as_list(values: float | Iterable[float] | None) -> list[float]:
    if values is None:
        return []
    if isinstance(values, (int, float)):
        return [float(values)]
    return [float(v) for v in values]


class CeaSession:
    """Набор веществ + решатели ядра. Создаётся один раз и используется для серии точек.

    Ядро использует глобальное состояние, поэтому экземпляр не предназначен для
    одновременного использования из нескольких потоков. Для параллельных серий
    используется `astra.core.batch` (отдельные процессы).
    """

    @_locked
    def __init__(self, propellant: Propellant, products: ProductOptions | None = None):
        _ensure_init()
        self.propellant = propellant
        self.products = products or ProductOptions()
        names = propellant.names
        try:
            self._reac = _cea.Mixture(names, ions=self.products.ions)
            if self.products.only:
                self._prod = _cea.Mixture(list(self.products.only), ions=self.products.ions)
            else:
                self._prod = _cea.Mixture(names, products_from_reactants=True,
                                          omit=list(self.products.omit), ions=self.products.ions)
        except (RuntimeError, ValueError) as exc:
            m = re.search(r"not found in ThermoDB: (\S+)", str(exc))
            if m:
                raise InputError(f"Вещество не найдено в базе NASA CEA: {m.group(1)}. "
                                 "Проверьте написание имени по базе веществ.") from exc
            raise InputError(f"Не удалось сформировать смесь из веществ {', '.join(names)}: {exc}") from exc

        amounts = np.array([c.amount for c in propellant.components], dtype=float)
        fuel = np.where([c.role == FUEL for c in propellant.components], amounts, 0.0)
        oxid = np.where([c.role == OXIDIZER for c in propellant.components], amounts, 0.0)
        if propellant.basis == "mole":
            fuel = np.asarray(self._reac.moles_to_weights(fuel), dtype=float)
            oxid = np.asarray(self._reac.moles_to_weights(oxid), dtype=float)
        self._fuel_w = fuel / fuel.sum()
        self._oxid_w = oxid / oxid.sum()
        self._t0 = np.array(propellant.temperatures, dtype=float)
        self._check_temperature_ranges()

        kw: dict[str, Any] = {"reactants": self._reac, "ions": self.products.ions,
                              "insert": list(self.products.insert)}
        if self.products.trace is not None:
            kw["trace"] = float(self.products.trace)
        self._solver_kw = kw
        self._eq_solver = None
        self._rocket_solver = None
        self.km0 = float(self._reac.weight_eq_ratio_to_of_ratio(self._oxid_w, self._fuel_w, 1.0))

    # ------------------------------------------------------------------ состав
    def _check_temperature_ranges(self) -> None:
        for comp in self.propellant.components:
            try:
                lo, hi = _cea.Reactant(comp.name).get_valid_temperature_range()
            except (RuntimeError, ValueError):
                continue
            # Для веществ с одной температурой (жидкие компоненты) ядро задаёт окно ±10 К.
            if not (lo - 1e-9 <= comp.t0 <= hi + 1e-9):
                raise InputError(
                    f"Начальная температура «{comp.name}» {comp.t0:g} К вне диапазона данных "
                    f"базы NASA CEA для этого вещества: {lo:g}…{hi:g} К."
                )

    def km(self, ratio: Ratio) -> float:
        """Kм для заданного соотношения (Kм или α)."""
        return ratio.value if ratio.kind == "Km" else ratio.value * self.km0

    def alpha(self, km: float) -> float:
        return km / self.km0

    @_locked
    def weights(self, km: float) -> np.ndarray:
        """Массы исходных веществ в порядке Propellant.components (ядро нормирует сумму)."""
        return np.asarray(self._reac.of_ratio_to_weights(self._oxid_w, self._fuel_w, float(km)), dtype=float)

    @_locked
    def reactant_property(self, km: float, which: str) -> float:
        """Свойство исходных компонентов при их начальных температурах, СИ.

        which: "i" — удельная энтальпия, Дж/кг; "u" — внутренняя энергия, Дж/кг;
               "s" — удельная энтропия, Дж/(кг·К).
        """
        code = {"i": _cea.ENTHALPY, "u": _cea.ENERGY, "s": _cea.ENTROPY}[which]
        return float(self._reac.calc_property(code, self.weights(km), self._t0))

    # ------------------------------------------------------------- равновесие
    def _eq(self):
        if self._eq_solver is None:
            self._eq_solver = _cea.EqSolver(self._prod, **self._solver_kw)
        return self._eq_solver

    @_locked
    def equilibrium(self, problem: str, ratio: Ratio, *, p: float | None = None, v: float | None = None,
                    t: float | None = None, i: float | None = None, s: float | None = None,
                    u: float | None = None) -> EquilibriumResult:
        """Равновесный расчёт в постановке TP, HP, SP, TV, UV или SV.

        Давление p — Па, удельный объём v — м³/кг, температура t — К,
        удельная энтальпия i и внутренняя энергия u — Дж/кг, энтропия s — Дж/(кг·К).
        Для HP, UV, SP, SV величина i, u, s, если не задана, берётся равной
        свойству исходных компонентов при их начальных температурах.
        """
        problem = problem.upper()
        if problem not in _PROBLEMS:
            raise InputError(f"Неизвестная постановка задачи равновесия: {problem}.")
        km = self.km(ratio)
        w = self.weights(km)

        first = problem[0]
        if first == "T":
            if t is None:
                raise InputError("Для этой постановки нужно задать температуру T.")
            q("t").check(t)
            state1 = t
        else:
            key = {"H": "i", "U": "u", "S": "s"}[first]
            given = {"i": i, "u": u, "s": s}[key]
            value = self.reactant_property(km, key) if given is None else float(given)
            state1 = value / R_UNIV   # ядро принимает h/R, u/R, s/R

        if problem[1] == "P":
            if p is None:
                raise InputError("Для этой постановки нужно задать давление P.")
            q("p").check(p)
            if p <= 0:
                raise InputError("Давление должно быть больше нуля.")
            state2 = p / BAR
        else:
            if v is None or not v > 0:
                raise InputError("Для этой постановки нужно задать положительный удельный объём v.")
            state2 = v

        solver = self._eq()
        soln = _cea.EqSolution(solver)
        msgs = _call_core(solver.solve, soln, getattr(_cea, problem), float(state1), float(state2), w)
        code = int(soln.last_error)
        converged = bool(soln.converged) and code == int(_cea.SUCCESS)
        values = {
            "t": float(soln.T), "p": float(soln.P) * BAR, "rho": float(soln.density),
            "v": float(soln.volume), "i": float(soln.enthalpy) * 1e3, "u": float(soln.energy) * 1e3,
            "s": float(soln.entropy) * 1e3, "g": float(soln.gibbs_energy) * 1e3,
            "cp": float(soln.cp_eq) * 1e3, "cp_fr": float(soln.cp_fr) * 1e3,
            "cv": float(soln.cv_eq) * 1e3, "cv_fr": float(soln.cv_fr) * 1e3,
            "k": float(soln.gamma_s), "mu": float(soln.MW), "mu_c": float(soln.M),
            "Km": km, "alpha": self.alpha(km),
        }
        # Скорость звука ядро в равновесном расчёте не выдаёт; она однозначно следует
        # из его величин так же, как в исходной программе: a = sqrt(k·R·T/μсм).
        values["a"] = math.sqrt(values["k"] * R_UNIV * values["t"] / values["mu_c"]) if converged else math.nan
        if not converged:
            values = {k: (v_ if k in ("Km", "alpha") else math.nan) for k, v_ in values.items()}
        point = StatePoint(
            kind="equilibrium", values=values,
            mole_fractions={k: float(x) for k, x in soln.mole_fractions.items()} if converged else {},
            mass_fractions={k: float(x) for k, x in soln.mass_fractions.items()} if converged else {},
        )
        inputs = {"problem": problem, "Km": km, "alpha": self.alpha(km), "p": p, "v": v, "t": t,
                  "i": i, "s": s, "u": u, "propellant": self.propellant, "products": self.products}
        message = _error_name(code) + (f" Сообщения ядра: {'; '.join(msgs)}." if msgs else "")
        return EquilibriumResult(problem, inputs, converged, code, message, point)

    # --------------------------------------------------------- камера и сопло
    def _rocket(self):
        if self._rocket_solver is None:
            self._rocket_solver = _cea.RocketSolver(self._prod, **self._solver_kw)
        return self._rocket_solver

    @_locked
    def nozzle(self, ratio: Ratio, pk: float, *,
               eps: Sequence[float] | float | None = None,
               pk_p: Sequence[float] | float | None = None,
               eps_sub: Sequence[float] | float | None = None,
               model: str = "equilibrium", freeze_at: str = "throat",
               tk: float | None = None, i: float | None = None,
               eps_k: float | None = None, mass_flux: float | None = None,
               pn: float | None = None, mdot: float | None = None) -> NozzleResult:
        """Расчёт камеры и сопла одним вызовом ядра (одно состояние камеры).

        pk       — давление в камере, Па;
        eps      — сверхзвуковые степени расширения ε = Fа/Fкр;
        pk_p     — отношения Pк/P для дополнительных сечений;
        eps_sub  — дозвуковые относительные площади;
        model    — "equilibrium" (равновесное) или "frozen" (замороженное расширение);
        freeze_at— для замороженного: "chamber" (состав камеры) или "throat" (состав в критике);
        tk       — задать температуру камеры вместо энтальпии (К);
        i        — удельная энтальпия камеры, Дж/кг (по умолчанию — энтальпия исходных компонентов);
        eps_k    — Fк/Fкр для камеры конечной площади (иначе камера бесконечной площади);
        mass_flux— ṁ/Fк, кг/(с·м²), альтернатива eps_k для камеры конечной площади;
        pn       — давление окружающей среды, Па (для Iуд(Pн) и режима истечения);
        mdot     — массовый расход, кг/с (для Fкр, Fа и тяги).
        """
        if model not in ("equilibrium", "frozen"):
            raise InputError("Модель течения: «equilibrium» (равновесная) или «frozen» (замороженная).")
        if model == "frozen" and freeze_at not in ("chamber", "throat"):
            raise InputError("Замораживание состава задаётся в камере («chamber») или в критическом сечении («throat»).")
        q("pk").check(pk)
        if tk is not None and i is not None:
            raise InputError("Задайте либо Tк, либо энтальпию камеры, но не обе величины.")
        if tk is not None:
            q("tk").check(tk)
        if eps_k is not None and mass_flux is not None:
            raise InputError("Для камеры конечной площади задайте либо Fк/Fкр, либо удельный расход.")
        if pn is not None and pn < 0:
            raise InputError("Давление окружающей среды Pн не может быть отрицательным.")
        if mdot is not None and not mdot > 0:
            raise InputError("Массовый расход ṁ должен быть положительным.")

        eps_l, pkp_l, sub_l = _as_list(eps), _as_list(pk_p), _as_list(eps_sub)
        for e in eps_l:
            if not e > 1.0:
                raise InputError(f"Сверхзвуковая степень расширения ε = {e:g} должна быть больше 1.")
        for r in pkp_l:
            if not r > 1.0:
                raise InputError(f"Отношение Pк/P = {r:g} должно быть больше 1.")
        for e in sub_l:
            if not e > 1.0:
                raise InputError(f"Дозвуковая относительная площадь {e:g} должна быть больше 1.")
        fac = eps_k is not None or mass_flux is not None
        if eps_k is not None and not eps_k > 1.0:
            raise InputError("Fк/Fкр должно быть больше 1.")

        km = self.km(ratio)
        w = self.weights(km)
        kwargs: dict[str, Any] = {"iac": not fac}
        if pkp_l:
            kwargs["pi_p"] = pkp_l
        if sub_l:
            kwargs["subar"] = sub_l
        if eps_l:
            kwargs["supar"] = eps_l
        if tk is not None:
            kwargs["tc"] = float(tk)
            i_used = None
        else:
            i_used = self.reactant_property(km, "i") if i is None else float(i)
            kwargs["hc"] = i_used / R_UNIV
        if eps_k is not None:
            kwargs["ac_at"] = float(eps_k)
        if mass_flux is not None:
            kwargs["mdot"] = float(mass_flux)
        if model == "frozen":
            # Номер точки замораживания в нумерации ядра:
            # IAC: 1 — камера, 2 — критика; FAC: 3 — конец камеры, 4 — критика.
            kwargs["n_frz"] = {(False, "chamber"): 1, (False, "throat"): 2,
                               (True, "chamber"): 3, (True, "throat"): 4}[(fac, freeze_at)]

        solver = self._rocket()
        soln = _cea.RocketSolution(solver)
        msgs = _call_core(solver.solve, soln, w, float(pk) / BAR, **kwargs)
        code = int(soln.last_error)
        converged = bool(soln.converged) and code == int(_cea.SUCCESS)

        kinds = (["injector", "chamber_inf", "chamber_end", "throat"] if fac else ["chamber", "throat"])
        kinds += ["pressure_ratio"] * len(pkp_l) + ["subsonic"] * len(sub_l) + ["supersonic"] * len(eps_l)
        n = int(soln.num_pts)
        points = self._rocket_points(soln, n, kinds, km, pk, pn, mdot)
        targets = [None] * (len(kinds) - len(pkp_l) - len(sub_l) - len(eps_l)) + pkp_l + sub_l + eps_l
        for pt, tgt in zip(points, targets):
            pt.target = tgt

        assumptions = [
            "Одномерное адиабатическое течение идеального газа без трения и теплообмена.",
            "Конденсированные фазы движутся с газом без скоростного и теплового отставания.",
            "Камера бесконечной площади (скорость в камере пренебрежимо мала)." if not fac
            else "Камера конечной площади: учитываются потери полного давления в камере.",
        ]
        if model == "equilibrium":
            assumptions.append("Равновесное расширение: состав в каждом сечении равновесный.")
        else:
            where = "камеры" if freeze_at == "chamber" else "критического сечения"
            assumptions.append(f"Замороженное расширение: состав зафиксирован на уровне {where}.")
        if pn is not None:
            assumptions.append("Iуд(Pн) рассчитан для безотрывного течения; отрыв потока не моделируется.")

        warns: list[str] = list(msgs)
        if n < len(kinds):
            warns.append(f"Ядро рассчитало {n} точек из {len(kinds)}; остальные не получены.")
        if pn is not None and any(p.regime == "over" for p in points):
            warns.append("Есть перерасширенные сечения (Pа < Pн): при сильном перерасширении в реальном сопле "
                         "возможен отрыв потока, который модель не учитывает.")

        inputs = {"Km": km, "alpha": self.alpha(km), "pk": pk, "eps": eps_l, "pk_p": pkp_l,
                  "eps_sub": sub_l, "model": model, "freeze_at": freeze_at if model == "frozen" else None,
                  "tk": tk, "i": i_used, "eps_k": eps_k, "mass_flux": mass_flux, "pn": pn, "mdot": mdot,
                  "propellant": self.propellant, "products": self.products}
        message = _error_name(code)
        return NozzleResult(model, inputs, converged, code, message, points, assumptions, warns)

    def _rocket_points(self, soln, n, kinds, km, pk, pn, mdot) -> list[StatePoint]:
        if n == 0:
            return []
        arr = lambda a: np.asarray(a, dtype=float)[:n]
        T, P, rho, vol = arr(soln.T), arr(soln.P) * BAR, arr(soln.density), arr(soln.volume)
        h, e, s, g = arr(soln.enthalpy) * 1e3, arr(soln.energy) * 1e3, arr(soln.entropy) * 1e3, arr(soln.gibbs_energy) * 1e3
        cp, cpf, cv, cvf = (arr(x) * 1e3 for x in (soln.cp_eq, soln.cp_fr, soln.cv_eq, soln.cv_fr))
        k, mw, m = arr(soln.gamma_s), arr(soln.MW), arr(soln.M)
        mach, a_s, ae = arr(soln.Mach), arr(soln.sonic_velocity), arr(soln.ae_at)
        cstar, cf, isp, ivac = arr(soln.c_star), arr(soln.coefficient_of_thrust), arr(soln.Isp), arr(soln.Isp_vacuum)
        xm = {sp: np.atleast_1d(np.asarray(v, dtype=float)) for sp, v in soln.mole_fractions.items()}
        xw = {sp: np.atleast_1d(np.asarray(v, dtype=float)) for sp, v in soln.mass_fractions.items()}

        pts: list[StatePoint] = []
        for j in range(n):
            kind = kinds[j] if j < len(kinds) else "supersonic"
            nozzle_section = kind in ("throat", "pressure_ratio", "subsonic", "supersonic")
            w_j = float(isp[j])  # скорость потока в сечении (в камере IAC равна 0)
            vals = {
                "t": T[j], "p": P[j], "rho": rho[j], "v": vol[j], "i": h[j], "u": e[j], "s": s[j], "g": g[j],
                "cp": cp[j], "cp_fr": cpf[j], "cv": cv[j], "cv_fr": cvf[j], "k": k[j], "mu": mw[j], "mu_c": m[j],
                "a": a_s[j], "M": mach[j], "w": w_j, "H": h[j] + 0.5 * w_j * w_j,
                "Km": km, "alpha": self.alpha(km), "pk": pk, "pk_p": pk / P[j] if P[j] > 0 else math.nan,
            }
            if nozzle_section:
                vals.update({
                    "eps": ae[j], "c_star": cstar[j], "kt": cf[j], "isp": isp[j], "isp_vac": ivac[j],
                    "kt_p": ivac[j] / cstar[j], "wa": w_j,
                })
            regime = None
            if nozzle_section and pn is not None:
                isp_amb = ivac[j] - pn * ae[j] * cstar[j] / pk
                vals["pn"] = pn
                vals["isp_amb"] = isp_amb
                vals["kt_n"] = isp_amb / cstar[j]
                if mdot is not None:
                    f_kr = mdot * cstar[j] / pk
                    vals.update({"mdot": mdot, "f_kr": f_kr, "f_a": ae[j] * f_kr, "thrust": isp_amb * mdot})
                if kind != "subsonic":
                    regime = classify_regime(P[j], pn)
            elif nozzle_section and mdot is not None:
                f_kr = mdot * cstar[j] / pk
                vals.update({"mdot": mdot, "f_kr": f_kr, "f_a": ae[j] * f_kr})
            pts.append(StatePoint(
                kind=kind, values={kk: float(vv) for kk, vv in vals.items()},
                mole_fractions={sp: float(v[j]) for sp, v in xm.items() if j < v.size},
                mass_fractions={sp: float(v[j]) for sp, v in xw.items() if j < v.size},
                regime=regime,
            ))
        return pts


def classify_regime(pa: float, pn: float, rel_tol: float = 1e-3) -> str:
    """Аэродинамический режим сопла по соотношению Pа и Pн (не зависит от химической модели)."""
    if pn == 0.0:
        return "vacuum"
    if abs(pa - pn) <= rel_tol * pn:
        return "design"
    return "under" if pa > pn else "over"
