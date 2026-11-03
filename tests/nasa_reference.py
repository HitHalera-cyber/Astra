"""Разбор эталонных выводов NASA CEA (формат `output long`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

REF_DIR = Path(__file__).parent / "reference" / "nasa_cea"

_ROW = re.compile(r"^ (\S.*?)\s{2,}(-?\d.*)$")
_PERF = {"Ae/At", "CSTAR, M/SEC", "CF", "Ivac, M/SEC", "Isp, M/SEC"}


@dataclass
class Block:
    header: str
    rows: dict[str, list[float]] = field(default_factory=dict)

    @property
    def frozen(self) -> bool:
        return "FROZEN" in self.header

    @property
    def ncols(self) -> int:
        return len(self.rows["P, BAR"])

    def value(self, label: str, col: int) -> float:
        """Значение в столбце col (0 — камера); строки характеристик выровнены по правому краю."""
        vals = self.rows[label]
        offset = self.ncols - len(vals)
        return vals[col - offset]


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
    for line in (REF_DIR / f"{name}.out").read_text(encoding="latin-1").splitlines():
        if "THEORETICAL ROCKET PERFORMANCE" in line or "THERMODYNAMIC EQUILIBRIUM" in line:
            cur = Block(line.strip())
            blocks.append(cur)
            continue
        if cur is None:
            continue
        if "FRACTIONS" in line:
            cur = None
            continue
        m = _ROW.match(line)
        if m:
            vals = _floats(m.group(2))
            if vals:
                cur.rows[m.group(1).strip()] = vals
    return [b for b in blocks if "P, BAR" in b.rows]


def omit_list(name: str) -> list[str]:
    """Список omit из входного файла задачи."""
    text = (REF_DIR / f"{name}.inp").read_text(encoding="latin-1")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(("#", "!"))]
    out: list[str] = []
    active = False
    for ln in lines:
        tokens = ln.split()
        if not tokens:
            continue
        if tokens[0].lower() == "omit":
            active, tokens = True, tokens[1:]
        elif tokens[0].lower() in ("end", "reac", "prob", "output", "outp", "only", "insert"):
            active = False
        if active:
            out.extend(tokens)
    return out
