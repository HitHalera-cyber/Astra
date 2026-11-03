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
from .notation import CHEMICAL_MODELS, NOZZLE_REGIMES, QUANTITIES, Quantity, q
from .propellant import FUEL, OXIDIZER, Component, ProductOptions, Propellant, Ratio
from .results import EquilibriumResult, NozzleResult, StatePoint
from .session import BAR, CeaSession, classify_regime, core_version
from . import grid

__all__ = [
    "AstraError", "BAR", "CHEMICAL_MODELS", "CeaSession", "Component", "CoreError", "EquilibriumResult",
    "FUEL", "InputError", "NOZZLE_REGIMES", "NozzleResult", "OXIDIZER", "ProductOptions", "Propellant",
    "QUANTITIES", "Quantity", "Ratio", "StatePoint", "Task", "TaskFailure", "classify_regime",
    "core_version", "grid", "q", "run_batch",
]
