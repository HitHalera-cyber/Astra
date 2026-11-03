"""База термодинамических веществ NASA CEA (чтение исходного файла thermo.inp).

Файл `astra/data/thermo.inp` — без изменений из репозитория NASA CEA 3.3.4
(NASA TP-2002-211556). Ядро в расчётах использует свою скомпилированную копию
`thermo.lib`; здесь база читается только для поиска и справки: формула,
фаза, молярная масса, энтальпия образования, температурные интервалы.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
import re


@dataclass(frozen=True)
class Species:
    name: str
    comment: str
    formula: tuple[tuple[str, float], ...]
    condensed: bool
    molar_mass: float              # г/моль
    hf: float                      # Дж/моль: энтальпия образования при 298,15 К
                                   # (для веществ без аппроксимации — энтальпия при T_assigned)
    t_ranges: tuple[tuple[float, float], ...]
    t_assigned: float | None       # для веществ, заданных при одной температуре (жидкие компоненты топлива)
    reactant_only: bool            # только исходное вещество (не продукт)
    ref_code: str

    @property
    def phase_name(self) -> str:
        if not self.condensed:
            return "газ"
        return "жидкость" if "(L)" in self.name else "конденсированная"

    @property
    def formula_text(self) -> str:
        """Брутто-формула; электрон «E» показывается зарядом иона (Ag⁺, O⁻, e⁻)."""
        parts, charge = [], 0.0
        for el, n in self.formula:
            if el.upper() == "E":
                charge -= n
                continue
            n_txt = f"{n:g}"
            parts.append(el.capitalize() + ("" if n_txt == "1" else n_txt))
        text = " ".join(parts)
        if charge:
            mag = f"{abs(charge):g}"
            sign = "⁺" if charge > 0 else "⁻"
            text = (text or "e") + ("" if mag == "1" else mag) + sign
        return text

    @property
    def t_min(self) -> float:
        return self.t_ranges[0][0] if self.t_ranges else (self.t_assigned or float("nan"))

    @property
    def t_max(self) -> float:
        return self.t_ranges[-1][1] if self.t_ranges else (self.t_assigned or float("nan"))

    @property
    def is_inert_copy(self) -> bool:
        return self.name.startswith("Inert")


def _f(text: str) -> float:
    text = text.strip().replace("D", "E").replace("d", "e")
    return float(text) if text else 0.0


def parse_thermo_inp(text: str) -> list[Species]:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].lower().startswith("thermo"):
        i += 1
    i += 2  # строка "thermo" и строка с границами интервалов
    out: list[Species] = []
    reactant_only = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("END PRODUCTS"):
            reactant_only = True
            i += 1
            continue
        if line.startswith("END REACTANTS") or line.startswith("END"):
            break
        if not line.strip() or line.startswith("!"):
            i += 1
            continue
        name = line[:18].strip()
        comment = line[18:].strip()
        rec = lines[i + 1].ljust(80)
        n_int = int(rec[0:2])
        ref = rec[3:9].strip()
        formula = []
        for k in range(5):
            el = rec[10 + 8 * k: 12 + 8 * k].strip()
            num = _f(rec[12 + 8 * k: 18 + 8 * k])
            if el and num != 0.0:
                formula.append((el, num))
        condensed = rec[50:52].strip() not in ("", "0")
        mw = _f(rec[52:65])
        hf = _f(rec[65:80])
        t_ranges: list[tuple[float, float]] = []
        t_assigned = None
        if n_int == 0:
            t_line = lines[i + 2]
            t_assigned = _f(t_line[0:11])
            i += 3
        else:
            for k in range(n_int):
                t_line = lines[i + 2 + 3 * k]
                t_ranges.append((_f(t_line[0:11]), _f(t_line[11:21])))
            i += 2 + 3 * n_int
        out.append(Species(name, comment, tuple(formula), condensed, mw, hf, tuple(t_ranges),
                           t_assigned, reactant_only, ref))
    return out


@lru_cache(maxsize=1)
def load() -> tuple[Species, ...]:
    text = resources.files("astra.data").joinpath("thermo.inp").read_text(encoding="latin-1")
    return tuple(parse_thermo_inp(text))


def by_name(name: str) -> Species | None:
    for s in load():
        if s.name == name:
            return s
    return None


def search(query: str, *, include_inert: bool = False, limit: int | None = None) -> list[Species]:
    """Поиск по имени, формуле и комментарию базы (без учёта регистра).

    Сначала идут точные совпадения имени, затем совпадения начала имени, затем остальные.
    include_inert — показывать служебные копии «Inert…» (инертные компоненты).
    """
    q = query.strip().lower()
    items = [s for s in load() if include_inert or not s.is_inert_copy]
    if not q:
        result = items
    else:
        q_compact = re.sub(r"\s+", "", q)
        scored = []
        for s in items:
            name = s.name.lower()
            formula = s.formula_text.lower().replace(" ", "")
            if name == q:
                rank = 0
            elif name.startswith(q):
                rank = 1
            elif q_compact == formula:
                rank = 2
            elif q in name:
                rank = 3
            elif q in s.comment.lower():
                rank = 4
            else:
                continue
            scored.append((rank, s.name, s))
        result = [s for _, _, s in sorted(scored, key=lambda t: (t[0], len(t[1]), t[1]))]
    return result[:limit] if limit else result
