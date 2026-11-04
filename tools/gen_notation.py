"""Таблица обозначений docs/oboznacheniya.md из astra.core.notation (единственный источник).

Запуск: python tools/gen_notation.py. Тест tests/test_docs.py проверяет, что файл актуален.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _range(qt) -> str:
    lo = None if math.isinf(qt.lower) else qt.to_display(qt.lower)
    hi = None if math.isinf(qt.upper) else qt.to_display(qt.upper)
    if lo is None and hi is None:
        return ""
    f = lambda v: f"{v:g}".replace(".", ",")  # noqa: E731
    return f"{f(lo) if lo is not None else '−∞'} … {f(hi) if hi is not None else '+∞'}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render() -> str:
    from astra.core import CHEMICAL_MODELS, NOZZLE_REGIMES, QUANTITIES, WAVE_PROBLEMS
    from astra.core.notation import EQUILIBRIUM_PROBLEMS
    lines = [
        "# Обозначения Astra",
        "",
        "Отечественная система обозначений, принятая в программе. Файл сформирован из "
        "`src/astra/core/notation.py` программой `tools/gen_notation.py` — правьте обозначения "
        "там, а не здесь.",
        "",
        "Внутри программы все величины хранятся в СИ; в интерфейсе, таблицах и отчётах они "
        "показываются в единицах из столбца «Единица». Обозначение γ не используется: показатель "
        "адиабаты — k. Массовое соотношение компонентов Kм и коэффициент избытка окислителя "
        "α = Kм / Kм⁰ — разные величины. i — удельная (статическая) энтальпия, "
        "H = i + W²/2 — полная энтальпия (энтальпия торможения).",
        "",
        "| Обозначение | Название | Физический смысл | Единица | Допустимые значения | Пояснение |",
        "|---|---|---|---|---|---|",
    ]
    for qt in QUANTITIES.values():
        lines.append("| " + " | ".join(_cell(x) for x in (qt.symbol, qt.name, qt.meaning, qt.unit, _range(qt),
                                                          qt.description)) + " |")
    for title, table in (("Модели течения в сопле", CHEMICAL_MODELS), ("Режимы истечения", NOZZLE_REGIMES),
                         ("Равновесные постановки", EQUILIBRIUM_PROBLEMS), ("Волновые задачи", WAVE_PROBLEMS)):
        lines += ["", f"## {title}", ""]
        lines += [f"- {v}" for v in table.values()]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    path = ROOT / "docs" / "oboznacheniya.md"
    path.write_text(render(), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"Записано: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
