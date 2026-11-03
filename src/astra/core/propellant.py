"""Исходные данные: компоненты топлива и соотношение компонентов."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .errors import InputError

FUEL = "fuel"
OXIDIZER = "oxidizer"
ROLE_NAMES = {FUEL: "горючее", OXIDIZER: "окислитель"}


@dataclass(frozen=True)
class Component:
    """Исходное вещество из базы NASA CEA.

    name    — имя вещества в базе (например, "H2(L)", "RP-1", "N2O4(L)");
    role    — FUEL или OXIDIZER;
    amount  — доля вещества внутри горючего или окислителя (массовая или
              мольная — см. Propellant.basis); доли нормируются ядром;
    t0      — начальная температура, К.
    """

    name: str
    role: str
    amount: float = 100.0
    t0: float = 298.15

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise InputError("Не задано имя вещества.")
        if self.role not in ROLE_NAMES:
            raise InputError(f"Роль компонента «{self.name}» должна быть «горючее» или «окислитель».")
        if not (self.amount > 0) or math.isinf(self.amount):
            raise InputError(f"Количество компонента «{self.name}» должно быть положительным.")
        if not (self.t0 > 0) or math.isinf(self.t0):
            raise InputError(f"Начальная температура компонента «{self.name}» должна быть больше 0 К.")


@dataclass(frozen=True)
class Propellant:
    """Топливо: набор горючих и окислителей.

    basis — "mass" (количества заданы в массовых долях) или "mole" (в мольных).
    """

    components: tuple[Component, ...]
    basis: str = "mass"

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", tuple(self.components))
        if self.basis not in ("mass", "mole"):
            raise InputError("Количество компонентов задаётся в массовых («mass») или мольных («mole») долях.")
        if not self.components:
            raise InputError("Не задано ни одного компонента топлива.")
        names = [c.name for c in self.components]
        if len(set(names)) != len(names):
            raise InputError("Одно и то же вещество указано несколько раз.")
        if not any(c.role == FUEL for c in self.components):
            raise InputError("Не задано горючее.")
        if not any(c.role == OXIDIZER for c in self.components):
            raise InputError("Не задан окислитель.")

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.components]

    @property
    def temperatures(self) -> list[float]:
        return [c.t0 for c in self.components]


@dataclass(frozen=True)
class Ratio:
    """Соотношение компонентов: Kм или α (взаимоисключающие способы задания)."""

    kind: str   # "Km" или "alpha"
    value: float

    def __post_init__(self) -> None:
        if self.kind not in ("Km", "alpha"):
            raise InputError("Соотношение компонентов задаётся через Kм или α.")
        if not (self.value > 0) or math.isinf(self.value):
            symbol = "Kм" if self.kind == "Km" else "α"
            raise InputError(f"{symbol} должно быть положительным числом.")

    @staticmethod
    def km(value: float) -> "Ratio":
        return Ratio("Km", float(value))

    @staticmethod
    def alpha(value: float) -> "Ratio":
        return Ratio("alpha", float(value))


@dataclass(frozen=True)
class ProductOptions:
    """Параметры набора продуктов, передаваемые ядру без изменений.

    only   — рассматривать только эти продукты (ключевое слово only в CEA);
    omit   — исключить эти продукты (omit);
    insert — конденсированные вещества для начального приближения (insert);
    ions   — учитывать ионы;
    trace  — порог малых компонентов (trace), None — по умолчанию ядра.
    """

    only: tuple[str, ...] = ()
    omit: tuple[str, ...] = ()
    insert: tuple[str, ...] = ()
    ions: bool = False
    trace: float | None = None

    def __post_init__(self) -> None:
        for name in ("only", "omit", "insert"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
