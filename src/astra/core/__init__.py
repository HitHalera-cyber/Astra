"""Программный интерфейс к вычислительному ядру NASA CEA.

Пример::

    from astra.core import CeaSession, Component, Propellant, Ratio, FUEL, OXIDIZER

    prop = Propellant((Component("H2(L)", FUEL, t0=20.27), Component("O2(L)", OXIDIZER, t0=90.17)))
    s = CeaSession(prop)
    r = s.nozzle(Ratio.km(5.55157), pk=53.3172e5, eps=[25, 50, 75], pn=0.0)
    print(r.chamber["t"], [p["isp_vac"] for p in r.exits()])
"""

from .batch import Task, TaskFailure, run_batch
from .errors import AstraError, CoreError, InputError
from .notation import CHEMICAL_MODELS, NOZZLE_REGIMES, QUANTITIES, WAVE_PROBLEMS, Quantity, q
from .propellant import FUEL, MIXTURE, OXIDIZER, Component, ProductOptions, Propellant, Ratio, formula_text, parse_formula
from .results import EquilibriumResult, NozzleResult, StatePoint, WaveResult
from .session import BAR, CeaSession, classify_regime, core_version, isp_at_ambient
from . import grid

__all__ = [
    "AstraError", "BAR", "CHEMICAL_MODELS", "CeaSession", "Component", "CoreError", "EquilibriumResult",
    "FUEL", "InputError", "MIXTURE", "NOZZLE_REGIMES", "NozzleResult", "OXIDIZER", "ProductOptions", "Propellant",
    "QUANTITIES", "Quantity", "Ratio", "StatePoint", "Task", "WAVE_PROBLEMS", "WaveResult", "TaskFailure", "classify_regime",
    "core_version", "formula_text", "grid", "isp_at_ambient", "parse_formula", "q", "run_batch",
]
