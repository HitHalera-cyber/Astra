"""Результаты расчётов.

Исходные данные (`inputs`) и вычисленные ядром величины (`values`) хранятся
раздельно. Все значения — в СИ, ключи — из `astra.core.notation.QUANTITIES`.
Величины, которые ядро не вычисляло для данной точки, равны NaN, а не нулю.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from .notation import CHEMICAL_MODELS, NOZZLE_REGIMES, POINT_KINDS, WAVE_PROBLEMS


@dataclass
class StatePoint:
    """Термодинамическое состояние в одной точке (камера, сечение сопла, равновесие)."""

    kind: str                                # ключ из POINT_KINDS или "equilibrium"
    values: dict[str, float]
    mole_fractions: dict[str, float] = field(default_factory=dict)
    mass_fractions: dict[str, float] = field(default_factory=dict)
    regime: str | None = None                # ключ из NOZZLE_REGIMES (только при заданном Pн)
    target: float | None = None              # заданное значение сечения (ε или Pк/P), W₁/M₁ или P₁
    case: int | None = None                  # номер варианта в серии (ударная волна, детонация)
    t_target: float | None = None            # заданная T₁ варианта (детонация)
    target_key: str | None = None            # какая величина задана в target: "u1" или "mach1" (ударная волна)

    @property
    def kind_name(self) -> str:
        return POINT_KINDS.get(self.kind, "Равновесное состояние")

    @property
    def regime_name(self) -> str | None:
        return NOZZLE_REGIMES.get(self.regime) if self.regime else None

    def __getitem__(self, key: str) -> float:
        return self.values.get(key, math.nan)

    def major_species(self, threshold: float = 5e-6, basis: str = "mole") -> dict[str, float]:
        """Компоненты продуктов с долей не ниже порога, по убыванию доли."""
        src = self.mole_fractions if basis == "mole" else self.mass_fractions
        items = [(k, v) for k, v in src.items() if v >= threshold]
        return dict(sorted(items, key=lambda kv: -kv[1]))


@dataclass
class EquilibriumResult:
    """Результат равновесного расчёта (TP, HP, SP, TV, UV, SV)."""

    problem: str
    inputs: dict[str, Any]
    converged: bool
    error_code: int
    message: str
    point: StatePoint

    def __getitem__(self, key: str) -> float:
        return self.point[key]


@dataclass
class NozzleResult:
    """Результат расчёта камеры и сопла при одном состоянии камеры.

    Все точки рассчитаны одним вызовом ядра от одного и того же состояния
    камеры, поэтому при изменении ε параметры камеры не меняются.
    """

    model: str                     # "equilibrium" или "frozen"
    inputs: dict[str, Any]
    converged: bool
    error_code: int
    message: str
    points: list[StatePoint]
    assumptions: list[str]
    warnings: list[str] = field(default_factory=list)

    @property
    def model_name(self) -> str:
        return CHEMICAL_MODELS[self.model]

    @property
    def chamber(self) -> StatePoint:
        for kind in ("chamber", "chamber_end"):
            for p in self.points:
                if p.kind == kind:
                    return p
        raise LookupError("В результате нет точки камеры сгорания.")

    @property
    def throat(self) -> StatePoint:
        for p in self.points:
            if p.kind == "throat":
                return p
        raise LookupError("В результате нет критического сечения.")

    def exits(self) -> list[StatePoint]:
        """Сечения после критического, в порядке задания."""
        return [p for p in self.points if p.kind in ("pressure_ratio", "subsonic", "supersonic")]

    def column(self, key: str, kinds: tuple[str, ...] | None = None) -> np.ndarray:
        pts = self.points if kinds is None else [p for p in self.points if p.kind in kinds]
        return np.array([p[key] for p in pts], dtype=float)


@dataclass
class WaveResult:
    """Результат расчёта ударной волны или детонации.

    problem — "shock" или "detonation". Для серии начальных условий (несколько
    W₁ или M₁) точки идут группами: для каждого варианта — состояние перед волной
    и за ней; StatePoint.target — заданное значение (W₁, M₁ или P₁), case — номер варианта.
    """

    problem: str
    inputs: dict[str, Any]
    converged: bool
    error_code: int
    message: str
    points: list[StatePoint]
    assumptions: list[str]
    warnings: list[str] = field(default_factory=list)
    cases: list[dict[str, Any]] = field(default_factory=list)   # по варианту: converged, error_code, message

    @property
    def problem_name(self) -> str:
        return WAVE_PROBLEMS[self.problem]

    def of_kind(self, kind: str) -> list[StatePoint]:
        return [p for p in self.points if p.kind == kind]
