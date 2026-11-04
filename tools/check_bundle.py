"""Проверка собранной папки программы: всё ли нужное для запуска лежит внутри неё.

Запуск после PyInstaller (Windows):  python tools/check_bundle.py dist/Astra

На машине сборки в C:\\Windows\\System32 установлен Visual C++ Redistributable, поэтому
самопроверка там проходит, даже если библиотеки времени выполнения C++ (vcruntime140.dll,
vcruntime140_1.dll, msvcp140.dll) не попали в сборку. На компьютере пользователя без этого
пакета NumPy и Qt тогда не загружаются («Importing the numpy C-extensions failed»).

Скрипт разбирает таблицы импорта всех .dll и .pyd сборки и требует, чтобы каждая
зависимость была либо системной библиотекой Windows (есть в System32), либо лежала в самой сборке, а
библиотеки Visual C++ — в папке _internal, откуда их находит загрузчик программы.
Код возврата 0 — сборка самодостаточна.
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import sys

import pefile  # ставится вместе с PyInstaller

# библиотеки Windows: всё из System32, кроме Visual C++ (UCRT — часть системы с Windows 10)
SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
# Visual C++ 2015–2022: на компьютере пользователя может не быть
VCRT = re.compile(r"^(vcruntime140(_1)?|msvcp140(_\d|_atomic_wait|_codecvt_ids)?|concrt140|vcomp140)\.dll$", re.I)


def imports(path: Path) -> list[str]:
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                               pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
    except pefile.PEFormatError:
        return []
    names = [e.dll.decode() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])]
    names += [e.dll.decode() for e in getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", [])]
    pe.close()
    return names


def check(root: Path) -> tuple[bool, list[str]]:
    internal = root / "_internal"
    files = [p for p in root.rglob("*") if p.suffix.lower() in (".dll", ".pyd", ".exe") and p.is_file()]
    present = {p.name.lower() for p in files}
    top = {p.name.lower() for p in internal.iterdir()} if internal.is_dir() else set()
    lines = [f"Проверка сборки {root}: {len(files)} библиотек"]
    missing: dict[str, set[str]] = {}
    for f in files:
        for dep in imports(f):
            low = dep.lower()
            if VCRT.match(low):
                ok = low in top or (f.parent / dep).exists()
            else:
                ok = low in present or low.startswith(("api-ms-win-", "ext-ms-")) or (SYSTEM32 / dep).exists()
            if not ok:
                missing.setdefault(dep, set()).add(str(f.relative_to(root)))
    vc = sorted(n for n in top if VCRT.match(n))
    lines.append("Visual C++ в _internal: " + (", ".join(vc) if vc else "нет"))
    for dep, users in sorted(missing.items()):
        lines.append(f"ОШИБКА  нет {dep}; нужна для: {', '.join(sorted(users)[:5])}"
                     + (f" и ещё {len(users) - 5}" if len(users) > 5 else ""))
    lines.append("ПРОЙДЕНО" if not missing else f"Не хватает библиотек: {len(missing)}")
    return not missing, lines


if __name__ == "__main__":
    ok, lines = check(Path(sys.argv[1] if len(sys.argv) > 1 else "dist/Astra"))
    print("\n".join(lines))
    sys.exit(0 if ok else 1)
