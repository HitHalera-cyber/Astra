"""Разбор эталонных выводов NASA CEA (формат `output long`).

Значения приводятся к единицам СИ-вывода CEA (бар, кДж/кг, кг/м³, Вт/(м·К)),
поэтому эталоны, напечатанные в атмосферах и калориях, сравниваются так же,
как напечатанные в СИ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

REF_DIR = Path(__file__).parent / "reference" / "nasa_cea"

_ROW = re.compile(r"^ (\S.*?)\s{2,}(-?\d.*)$")
_HEADERS = ("THEORETICAL ROCKET PERFORMANCE", "THERMODYNAMIC EQUILIBRIUM", "SHOCK WAVE PARAMETERS",
            "DETONATION PROPERTIES")
# Подразделы, внутри которых повторяются одни и те же подписи строк.
_SECTIONS = ("INITIAL GAS", "SHOCKED GAS", "UNBURNED GAS", "BURNED GAS", "DETONATION PARAMETERS",
             "WITH EQUILIBRIUM REACTIONS", "WITH FROZEN REACTIONS")

CAL = 4.184  # кал/г → кДж/кг, кал/(г·К) → кДж/(кг·К)
# подпись в несистемных единицах → (подпись в СИ, множитель)
_UNITS = {
    "P, ATM": ("P, BAR", 1.01325),
    "P1, ATM": ("P1, BAR", 1.01325),
    "RHO, G/CC": ("RHO, KG/CU M", 1000.0),
    "H, CAL/G": ("H, KJ/KG", CAL),
    "H1, CAL/G": ("H1, KJ/KG", CAL),
    "U, CAL/G": ("U, KJ/KG", CAL),
    "G, CAL/G": ("G, KJ/KG", CAL),
    "S, CAL/(G)(K)": ("S, KJ/(KG)(K)", CAL),
    "Cp, CAL/(G)(K)": ("Cp, KJ/(KG)(K)", CAL),
}
# теплопроводность → Вт/(м·К)
_COND = {"MILLICALORIES/(CM)(K)(SEC)": 0.4184, "MILLIWATTS/(CM)(K)": 0.1}


@dataclass
class Block:
    header: str
    rows: dict[str, list[float]] = field(default_factory=dict)
    sections: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    text: list[str] = field(default_factory=list)

    @property
    def frozen(self) -> bool:
        return "FROZEN" in self.header

    @property
    def ncols(self) -> int:
        for key in ("P, BAR", "P1, BAR"):
            if key in self.rows:
                return len(self.rows[key])
        return max(len(v) for v in self.rows.values())

    def value(self, label: str, col: int, section: str | None = None) -> float:
        """Значение в столбце col (0 — камера); строки характеристик выровнены по правому краю."""
        vals = (self.sections[section] if section else self.rows)[label]
        offset = self.ncols - len(vals)
        return vals[col - offset]

    def section(self, prefix: str) -> dict[str, list[float]]:
        for name, rows in self.sections.items():
            if name.startswith(prefix):
                return rows
        raise KeyError(prefix)

    def scalar(self, name: str) -> float:
        """Число после «name=» в заголовке блока (например, O/F)."""
        for line in self.text:
            m = re.search(re.escape(name) + r"\s*=\s*(-?[\d.]+E?[-+]?\d*)", line)
            if m:
                return float(m.group(1))
        raise KeyError(name)


def _floats(text: str) -> list[float] | None:
    out = []
    for tok in text.split():
        try:
            out.append(float(tok))
        except ValueError:
            return None
    return out


def parse(name: str) -> list[Block]:
    blocks: list[Block] = []
    cur: Block | None = None
    section = ""
    cond = 1.0
    for line in (REF_DIR / f"{name}.out").read_text(encoding="latin-1").splitlines():
        stripped = line.strip()
        if any(h in line for h in _HEADERS):
            cur = Block(stripped)
            blocks.append(cur)
            section, cond = "", 1.0
            continue
        if cur is None:
            continue
        if "FRACTIONS" in line:
            cur = None
            continue
        cur.text.append(line)
        if any(stripped.startswith(s) for s in _SECTIONS):
            section = stripped
            cur.sections.setdefault(section, {})
            continue
        for unit, factor in _COND.items():
            if "CONDUCTIVITY IN UNITS OF " + unit in line:
                cond = factor
        m = _ROW.match(line)
        if m:
            vals = _floats(m.group(2))
            if vals:
                label = m.group(1).strip()
                if label in _UNITS:
                    label, factor = _UNITS[label]
                    vals = [v * factor for v in vals]
                if label == "CONDUCTIVITY":
                    vals = [v * cond for v in vals]
                cur.rows.setdefault(label, vals)   # повторы (Cp в разделе переносных свойств) — только в sections
                if section:
                    cur.sections[section][label] = vals
    return [b for b in blocks if b.rows]


def _dataset(name: str, keyword: str) -> list[str]:
    text = (REF_DIR / f"{name}.inp").read_text(encoding="latin-1")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(("#", "!"))]
    out: list[str] = []
    active = False
    for ln in lines:
        tokens = ln.split()
        if not tokens:
            continue
        if tokens[0].lower() == keyword:
            active, tokens = True, tokens[1:]
        elif tokens[0].lower() in ("end", "reac", "prob", "problem", "output", "outp", "only", "omit", "insert"):
            active = False
        if active:
            out.extend(tokens)
    return out


def omit_list(name: str) -> list[str]:
    """Список omit из входного файла задачи."""
    return _dataset(name, "omit")


def only_list(name: str) -> list[str]:
    """Список only из входного файла задачи."""
    return _dataset(name, "only")
