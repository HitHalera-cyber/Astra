"""Самопроверка установленной программы: ядро NASA CEA, база веществ, параллельный расчёт.

Запуск: «Astra.exe --selftest отчёт.txt» (или python -m astra --selftest). Сверяет задачу
RP-1311 №8 (H2(L)/O2(L), Kм = 5,55157, Pк = 53,3172 бар) с эталонным выводом NASA CEA,
проверяет чтение базы веществ и серию в нескольких процессах (так в собранной программе
проверяется запуск дочерних процессов). Код возврата 0 — все проверки пройдены.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import traceback

# эталон NASA CEA, tests/reference/nasa_cea/example8.out: камера бесконечной площади, равновесное
EX8 = {
    "chamber_t": 3383.84462594510,
    "c_star": 2332.33560769645,
    "eps": [25.0, 50.0, 75.0],
    "isp_vac": [4348.51382282217, 4487.30214700488, 4554.91082019847],
    "isp": [4124.41484261268, 4309.12160403171, 4399.11825930155],
}
REL = 5e-4


def _check(lines: list[str], name: str, got: float, want: float, rel: float = REL) -> bool:
    ok = math.isfinite(got) and math.isclose(got, want, rel_tol=rel)
    lines.append(f"{'ПРОЙДЕНО' if ok else 'ОШИБКА  '}  {name}: Astra {got:.6g}, NASA {want:.6g}")
    return ok


def run() -> tuple[bool, list[str]]:
    from astra.core import CeaSession, Component, FUEL, OXIDIZER, Propellant, Ratio, core_version, species_db
    from astra.projects import AxisSpec, Project, StudySpec
    from astra.projects.study import run_study

    lines = [f"Самопроверка Astra, ядро NASA CEA {core_version()}, Python {sys.version.split()[0]}"]
    ok = True
    prop = Propellant((Component("H2(L)", FUEL, t0=20.27), Component("O2(L)", OXIDIZER, t0=90.17)))
    res = CeaSession(prop).nozzle(Ratio.km(5.55157), 53.3172e5, eps=EX8["eps"])
    ok &= bool(res.converged)
    lines.append(f"{'ПРОЙДЕНО' if res.converged else 'ОШИБКА  '}  сходимость ядра: {res.message}")
    ok &= _check(lines, "Tк, К", res.chamber["t"], EX8["chamber_t"])
    exits = [p for p in res.points if p.kind == "supersonic"]
    ok &= _check(lines, "C*, м/с", exits[0]["c_star"], EX8["c_star"])
    for p, e, iv, isp in zip(exits, EX8["eps"], EX8["isp_vac"], EX8["isp"]):
        ok &= _check(lines, f"Iуд.п при ε = {e:g}, м/с", p["isp_vac"], iv)
        ok &= _check(lines, f"Iуд при ε = {e:g}, м/с", p["isp"], isp)

    n = len(species_db.load())
    good = n > 1000 and species_db.by_name("H2O") is not None
    ok &= good
    lines.append(f"{'ПРОЙДЕНО' if good else 'ОШИБКА  '}  база веществ: {n} записей")

    p = Project.example()
    p.study = StudySpec(axes=[AxisSpec("alpha", "count", 0.6, 1.0, 0.1, 4)])
    one = run_study(p, workers=1)
    two = run_study(p, workers=2)
    same = all(one.value(i, "isp_vac") == two.value(i, "isp_vac") for i in range(len(one))) and one.n_failed == 0
    ok &= same
    lines.append(f"{'ПРОЙДЕНО' if same else 'ОШИБКА  '}  серия в двух процессах совпадает с расчётом в одном")
    gui_ok, gui_text = _gui()
    ok &= gui_ok
    lines.append(f"{'ПРОЙДЕНО' if gui_ok else 'ОШИБКА  '}  интерфейс: {gui_text}")
    lines.append("ИТОГ: " + ("все проверки пройдены" if ok else "ЕСТЬ ОШИБКИ"))
    return ok, lines


def _gui() -> tuple[bool, str]:
    """Главное окно создаётся, все разделы открываются, расчёт из раздела выполняется."""
    import tempfile
    from PySide6.QtWidgets import QApplication
    from astra.app.main import create_window, install_russian_qt
    from astra.app.main_window import SECTIONS
    app = QApplication.instance() or QApplication(sys.argv[:1])
    install_russian_qt(app)
    with tempfile.TemporaryDirectory() as tmp:
        win = create_window(Path(tmp) / "selftest.sqlite")
        for key, _ in SECTIONS:
            win.go_to(key)
            app.processEvents()
        page = win.pages["thermo"]
        page.run()
        page.thread.wait(60000)
        app.processEvents()
        status = page.status.text()
        good = page.status.objectName() == "Good" and win.state.last_result is not None
        win.state.store.close() if hasattr(win.state.store, "close") else None
        win.close()
        win.deleteLater()
        app.processEvents()
    return good, f"{len(SECTIONS)} разделов открыты; расчёт из раздела: {status}"


def main(out: str | None = None) -> int:
    try:
        ok, lines = run()
    except Exception:
        ok, lines = False, ["ОШИБКА самопроверки:", traceback.format_exc()]
    text = "\n".join(lines) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
    if sys.stdout is not None:      # в оконной сборке консоли нет
        try:
            sys.stdout.write(text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(text.encode("utf-8"))
    return 0 if ok else 1
