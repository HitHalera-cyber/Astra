"""Исходные данные: компоненты топлива и соотношение компонентов."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re

from .errors import InputError

FUEL = "fuel"
OXIDIZER = "oxidizer"
MIXTURE = "mixture"   # компонент готовой смеси без деления на горючее и окислитель (name= в NASA CEA)
ROLE_NAMES = {FUEL: "горючее", OXIDIZER: "окислитель", MIXTURE: "компонент смеси"}

# Символы элементов, которые знает ядро NASA CEA (в ядре они записываются прописными: CL, AL…).
ELEMENTS = frozenset("""
H HE LI BE B C N O F NE NA MG AL SI P S CL AR K CA SC TI V CR MN FE CO NI CU ZN GA GE AS SE BR KR
RB SR Y ZR NB MO TC RU RH PD AG CD IN SN SB TE I XE CS BA LA CE PR ND PM SM EU GD TB DY HO ER TM
YB LU HF TA W RE OS IR PT AU HG TL PB BI PO AT RN FR RA AC TH PA U NP PU AM CM BK CF ES D
""".split())

_FORMULA_TOKEN = re.compile(r"\s*([A-Za-z]{1,2})\s*[:=]?\s*([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?)\s*;?")


def parse_formula(text: str) -> tuple[tuple[str, float], ...]:
    """Брутто-формула в записи NASA CEA: «C 1 H 1.86955 O 0.031256» (или «C1 H1,87 O0,03»).

    После каждого символа элемента обязательно указывается число атомов (может быть дробным).
    Символы приводятся к записи ядра (прописные буквы).
    """
    text = (text or "").strip()
    if not text:
        raise InputError("Не задана формула вещества.")
    out: dict[str, float] = {}
    pos = 0
    while pos < len(text):
        m = _FORMULA_TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise InputError(f"Не удалось разобрать формулу «{text}» с позиции {pos + 1}. Запись: символ элемента "
                             "и число атомов, например «C 1 H 1.86955 O 0.031256».")
        sym, num = m.group(1).upper(), float(m.group(2).replace(",", "."))
        if sym not in ELEMENTS:
            raise InputError(f"«{m.group(1)}» — не символ химического элемента.")
        if sym in out:
            raise InputError(f"Элемент {sym} указан в формуле дважды.")
        out[sym] = num
        pos = m.end()
    return tuple(out.items())


def formula_text(formula) -> str:
    return " ".join(f"{el} {n:g}" for el, n in formula)


@dataclass(frozen=True)
class Component:
    """Исходное вещество: из базы NASA CEA или собственное (с формулой, заданной пользователем).

    name    — имя вещества в базе (например, "H2(L)", "RP-1", "N2O4(L)") или имя
              собственного вещества;
    role    — FUEL, OXIDIZER или MIXTURE;
    amount  — доля вещества внутри горючего или окислителя, а для MIXTURE —
              доля в смеси (массовая или мольная — см. Propellant.basis);
              доли нормируются ядром;
    t0      — начальная температура, К;
    formula — для собственного вещества: брутто-формула ((элемент, число атомов), …);
    enthalpy — для собственного вещества: энтальпия при T₀, Дж/моль (при T₀ = 298,15 К —
              теплота образования ΔHf°), как в задаче NASA RP-1311 №5;
    mw      — молярная масса собственного вещества, г/моль; None — ядро рассчитывает её
              по формуле.
    """

    name: str
    role: str
    amount: float = 100.0
    t0: float = 298.15
    formula: tuple[tuple[str, float], ...] = ()
    enthalpy: float | None = None
    mw: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "formula", tuple((str(el).upper(), float(n)) for el, n in
                                                  (self.formula.items() if isinstance(self.formula, dict)
                                                   else self.formula)))
        if not self.name or not self.name.strip():
            raise InputError("Не задано имя вещества.")
        if self.role not in ROLE_NAMES:
            raise InputError(f"Роль компонента «{self.name}» должна быть «горючее», «окислитель» "
                             "или «компонент смеси».")
        if not (self.amount > 0) or math.isinf(self.amount):
            raise InputError(f"Количество компонента «{self.name}» должно быть положительным.")
        if not (self.t0 > 0) or math.isinf(self.t0):
            raise InputError(f"Начальная температура компонента «{self.name}» должна быть больше 0 К.")
        if self.formula:
            if not re.fullmatch(r"[\x21-\x7e]{1,15}", self.name):
                raise InputError(f"Имя собственного вещества «{self.name}» записывается латиницей, цифрами и "
                                 "знаками без пробелов, не длиннее 15 символов (ограничение ядра NASA CEA).")
            for el, n in self.formula:
                if el not in ELEMENTS:
                    raise InputError(f"В формуле «{self.name}»: «{el}» — не символ химического элемента.")
                if not (n > 0) or math.isinf(n):
                    raise InputError(f"В формуле «{self.name}» число атомов {el} должно быть положительным.")
            if len({el for el, _ in self.formula}) != len(self.formula):
                raise InputError(f"В формуле «{self.name}» элемент указан дважды.")
            if self.enthalpy is None or not math.isfinite(self.enthalpy):
                raise InputError(f"Для собственного вещества «{self.name}» нужно задать энтальпию, кДж/моль.")
            if self.mw is not None and (not (self.mw > 0) or math.isinf(self.mw)):
                raise InputError(f"Молярная масса «{self.name}» должна быть положительной.")
        elif self.enthalpy is not None or self.mw is not None:
            raise InputError(f"Энтальпия и молярная масса задаются только для собственного вещества "
                             f"с формулой, а «{self.name}» берётся из базы NASA CEA.")

    @property
    def is_custom(self) -> bool:
        """Собственное вещество с формулой, заданной пользователем (не из базы NASA CEA)."""
        return bool(self.formula)


@dataclass(frozen=True)
class Propellant:
    """Топливо: набор горючих и окислителей либо готовая смесь.

    basis — "mass" (количества заданы в массовых долях) или "mole" (в мольных).
    Если все компоненты имеют роль MIXTURE, состав задан напрямую и соотношение
    компонентов (Kм, α) не используется.
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
        roles = {c.role for c in self.components}
        if MIXTURE in roles:
            if roles != {MIXTURE}:
                raise InputError("Компоненты смеси нельзя сочетать с горючим и окислителем: "
                                 "задайте либо горючее и окислитель, либо состав смеси целиком.")
            return
        if FUEL not in roles:
            raise InputError("Не задано горючее.")
        if OXIDIZER not in roles:
            raise InputError("Не задан окислитель.")

    @property
    def is_mixture(self) -> bool:
        """Состав задан смесью целиком (Kм и α не определены)."""
        return all(c.role == MIXTURE for c in self.components)

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
    trace  — порог малых компонентов (trace), None — по умолчанию ядра;
    transport — рассчитывать переносные свойства (вязкость, теплопроводность, Pr).
    """

    only: tuple[str, ...] = ()
    omit: tuple[str, ...] = ()
    insert: tuple[str, ...] = ()
    ions: bool = False
    trace: float | None = None
    transport: bool = False

    def __post_init__(self) -> None:
        for name in ("only", "omit", "insert"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if self.only and self.omit:
            raise InputError("Списки «только эти продукты» и «исключить продукты» не задаются одновременно.")
        if self.trace is not None and not (0.0 < self.trace < 1.0):
            raise InputError("Порог малых компонентов trace должен быть в интервале (0; 1).")
