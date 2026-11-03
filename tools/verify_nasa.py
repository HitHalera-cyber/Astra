"""Отчёт о сверке Astra с эталонными выводами NASA CEA.

Запускает эталонные тесты (tests/test_nasa_reference*.py) и записывает таблицу
наибольших относительных расхождений по задачам и величинам в
docs/etap-8-verification.md. Запуск: python tools/verify_nasa.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

TITLES = {
    "test_example1_tp_assigned_t_and_p": "№1 TP: H2/воздух, заданные T и P",
    "test_example2_tv_with_transport": "№2 TV: H2/воздух, переносные свойства",
    "test_example3_hp_multicomponent": "№3 HP: воздух + толуол/н-октан",
    "test_example4_uv_assigned_energy_and_density": "№4 UV: заданные u и ρ",
    "test_example6_chapman_jouguet_detonation": "№6 Детонация Чепмена – Жуге H2/O2",
    "test_example7_incident_shock[False]": "№7 Падающая ударная волна, равновесный состав",
    "test_example7_incident_shock[True]": "№7 Падающая ударная волна, замороженный состав",
    "test_example8_rocket_equilibrium": "№8 Камера и сопло, равновесное: H2(L)/O2(L)",
    "test_finite_area_combustor[example9-fac0]": "№9 Камера конечной площади, Fк/Fкр = 1,58",
    "test_finite_area_combustor[example10-fac1]": "№10 Камера конечной площади, ṁ/Fк",
    "test_example11_ions_mole_basis_transport": "№11 Li/F2 с ионами, переносные свойства",
    "test_example12_rocket_frozen_at_throat": "№12 Замороженное с критики: CH6N2/N2O4",
    "test_example13_tripropellant_insert_trace": "№13 N2H4 + Be / H2O2, insert, trace",
    "test_example14_tp_with_condensation": "№14 TP с конденсацией воды",
}


def run() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "dev.json"
        env = {**os.environ, "ASTRA_VERIFY_REPORT": str(out), "QT_QPA_PLATFORM": "offscreen"}
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "tests/test_nasa_reference.py", "tests/test_nasa_reference_modes.py"],
                       cwd=ROOT, env=env, check=False)
        return json.loads(out.read_text(encoding="utf-8"))


def fmt(x: float) -> str:
    return "0" if x == 0 else f"{x:.1e}".replace(".", ",")


def render(data: dict) -> str:
    from astra.core import core_version
    by_test: dict[str, list[dict]] = defaultdict(list)
    for r in data["rows"]:
        by_test[r["test"]].append(r)
    total = sum(r["count"] for r in data["rows"])
    worst = max(data["rows"], key=lambda r: r["max_rel"])
    ok = data["exitstatus"] == 0
    lines = [
        "# Этап 8. Сверка с эталонами NASA CEA",
        "",
        f"Отчёт сформирован {date.today():%d.%m.%Y} программой `tools/verify_nasa.py` по эталонным тестам "
        f"`tests/test_nasa_reference*.py`; ядро NASA CEA {core_version()}.",
        "",
        "Каждая величина, которую печатает оригинальная программа NASA CEA в эталонных выводах "
        "(`tests/reference/nasa_cea/*.out`, задачи RP-1311), сравнивается со значением, которое Astra "
        "получает через свой адаптер (единицы СИ, отечественные обозначения) и переводит обратно в единицы "
        "эталона. Сравнение — с тем числом значащих цифр, которое напечатано в эталоне, поэтому расхождение "
        "порядка 1e-5…1e-4 — это округление печати NASA, а не погрешность расчёта.",
        "",
        f"**Итог: {'все сравнения в допуске' if ok else 'ЕСТЬ РАСХОЖДЕНИЯ ВНЕ ДОПУСКА — см. вывод pytest'}.** "
        f"Сравнений: {total}; наибольшее относительное расхождение {fmt(worst['max_rel'])} "
        f"({worst['quantity']}, {TITLES.get(worst['test'], worst['test'])}); допуск 5e-4.",
        "",
        "Задача №5 (реагент с формулой, заданной пользователем) не проверяется: ввод собственных "
        "реагентов в Astra пока не поддерживается.",
        "",
    ]
    for test in sorted(by_test, key=lambda t: list(TITLES).index(t) if t in TITLES else 99):
        rows = by_test[test]
        lines += [f"## {TITLES.get(test, test)}", "",
                  "| Величина (подпись NASA) | Сравнений | Наибольшее отн. расхождение | Допуск |",
                  "|---|---:|---:|---:|"]
        for r in sorted(rows, key=lambda r: r["quantity"]):
            nz = f" (из них около нуля: {r['near_zero']})" if r["near_zero"] else ""
            lines.append(f"| {r['quantity']} | {r['count']}{nz} | {fmt(r['max_rel'])} | {fmt(r['tol'])} |")
        lines.append("")
    lines += ["Значения около нуля (например, число Маха в камере) сравниваются по абсолютному допуску 1e-6 "
              "и в относительное расхождение не входят.", ""]
    return "\n".join(lines)


def main() -> int:
    data = run()
    text = render(data)
    path = ROOT / "docs" / "etap-8-verification.md"
    path.write_text(text, encoding="utf-8")
    print(f"Отчёт записан: {path}")
    return data["exitstatus"]


if __name__ == "__main__":
    sys.exit(main())
