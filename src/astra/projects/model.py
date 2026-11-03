"""Модель проекта. Хранит только исходные данные (в СИ); результаты — в журнале."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from astra.core import Component, ProductOptions, Propellant, Ratio


@dataclass
class ComponentSpec:
    name: str
    role: str            # "fuel" | "oxidizer"
    amount: float = 100.0
    t0: float = 298.15

    def to_core(self) -> Component:
        return Component(self.name, self.role, float(self.amount), float(self.t0))


@dataclass
class Conditions:
    """Исходные условия расчёта (все величины в СИ)."""

    basis: str = "mass"            # доли компонентов: "mass" | "mole"
    ratio_kind: str = "alpha"      # "Km" | "alpha"
    ratio_value: float = 0.8
    calc: str = "rocket"           # "rocket" (камера и сопло) или постановка равновесия TP/HP/...
    pk: float = 10.0e6             # Па
    t: float = 3000.0              # К (для TP, TV и при заданной Tк)
    v: float = 1.0                 # м³/кг (для TV, UV, SV)
    chamber_by_tk: bool = False    # камера задаётся температурой вместо энтальпии компонентов
    eps: list[float] = field(default_factory=lambda: [10.0, 50.0, 100.0])
    pk_p: list[float] = field(default_factory=list)
    model: str = "equilibrium"     # "equilibrium" | "frozen"
    freeze_at: str = "throat"      # "chamber" | "throat"
    pn: float | None = 101325.0    # Па; None — не учитывать внешнее давление
    mdot: float | None = None      # кг/с
    eps_k: float | None = None     # Fк/Fкр; None — камера бесконечной площади
    ions: bool = False

    def ratio(self) -> Ratio:
        return Ratio(self.ratio_kind, float(self.ratio_value))


@dataclass
class Project:
    name: str = "Новый проект"
    description: str = ""
    components: list[ComponentSpec] = field(default_factory=list)
    conditions: Conditions = field(default_factory=Conditions)
    id: int | None = None
    created: str = ""
    modified: str = ""

    def propellant(self) -> Propellant:
        return Propellant(tuple(c.to_core() for c in self.components), basis=self.conditions.basis)

    def products(self) -> ProductOptions:
        return ProductOptions(ions=self.conditions.ions)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("id", "created", "modified"):
            d.pop(k)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Project":
        comps = [ComponentSpec(**c) for c in d.get("components", [])]
        cond = Conditions(**d.get("conditions", {}))
        return Project(name=d.get("name", "Проект"), description=d.get("description", ""),
                       components=comps, conditions=cond)

    @staticmethod
    def example() -> "Project":
        """Пример: H2(L)/O2(L) — задача RP-1311 №8 по составу компонентов."""
        return Project(
            name="Пример: водород + кислород",
            components=[ComponentSpec("H2(L)", "fuel", 100.0, 20.27),
                        ComponentSpec("O2(L)", "oxidizer", 100.0, 90.17)],
            conditions=Conditions(ratio_kind="Km", ratio_value=5.55157, pk=53.3172e5, eps=[25.0, 50.0, 75.0]),
        )


@dataclass
class CalcRecord:
    """Запись журнала расчётов: что считали, с какими исходными данными и что получили."""

    id: int | None
    project_id: int
    timestamp: str
    kind: str                   # "rocket" | "TP" | "HP" ...
    inputs: dict[str, Any]
    results: dict[str, Any]
    converged: bool
    message: str
    core_version: str
