"""Точка входа собранной программы (PyInstaller)."""

import multiprocessing
import os
import sys

# OpenBLAS (внутри NumPy) при загрузке выделяет буферы на каждый поток процессора; на
# компьютерах с большим числом ядер и малым файлом подкачки это заканчивается ошибкой
# «Произошел сбой в программе инициализации библиотеки DLL» (код 1114). Расчётам Astra
# много потоков линейной алгебры не нужно; заданное пользователем значение сохраняется.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")


def _startup_report(exc: BaseException) -> str:
    """Подробности сбоя запуска: текст ошибки и состав папки программы."""
    from pathlib import Path
    import platform
    import traceback

    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    lines = [
        "Astra не запустилась. Пришлите этот файл разработчику.",
        "",
        f"Программа: {sys.executable}",
        f"Windows: {platform.platform()}, процессор: {platform.processor() or platform.machine()}",
        f"Python: {sys.version}",
        f"Ядер процессора: {os.cpu_count()}, OPENBLAS_NUM_THREADS={os.environ.get('OPENBLAS_NUM_THREADS')}",
        "",
        "".join(traceback.format_exception(exc)),
        "Библиотеки Visual C++ в папке программы:",
    ]
    for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
        lines.append(f"  {name}: {'есть' if (base / name).is_file() else 'НЕТ'}")
    libs = base / "numpy.libs"
    lines.append(f"numpy.libs: {', '.join(sorted(os.listdir(libs))) if libs.is_dir() else 'НЕТ ПАПКИ'}")
    core = base / "numpy" / "_core"
    pyd = sorted(p.name for p in core.glob("*.pyd")) if core.is_dir() else []
    lines.append(f"numpy/_core: {len(pyd)} модулей .pyd{'' if pyd else ' — НЕТ'}")
    return "\n".join(lines) + "\n"


def _report_failure(exc: BaseException) -> None:
    from pathlib import Path

    text = _startup_report(exc)
    target = None
    for d in (os.environ.get("LOCALAPPDATA"), os.environ.get("TEMP"), str(Path.home())):
        if not d:
            continue
        try:
            folder = Path(d) / "Astra"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / "ошибка-запуска.txt"
            target.write_text(text, encoding="utf-8")
            break
        except OSError:
            target = None
    # при самопроверке отчёт пишется в указанный файл, окно не показывается
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        try:
            Path(sys.argv[2]).write_text(text, encoding="utf-8")
        except OSError:
            pass
        return
    if sys.platform == "win32":
        import ctypes

        first = str(exc).strip().splitlines()
        msg = ("Astra не удалось запустить.\n\n"
               + (f"Подробности сохранены в файле:\n{target}\n\n" if target else "")
               + "Пришлите этот файл разработчику.\n\nКратко: "
               + (first[-1] if first else type(exc).__name__))
        ctypes.windll.user32.MessageBoxW(None, msg, "Astra — ошибка запуска", 0x10)
    else:
        sys.stderr.write(text)


if __name__ == "__main__":
    # дочерние процессы пакетных серий запускаются тем же exe: freeze_support
    # передаёт им управление, и окно программы в них не открывается
    multiprocessing.freeze_support()
    try:
        from astra.app.main import main
        code = main()
    except Exception as exc:  # сбой загрузки библиотек (NumPy, Qt, ядро) — сохраняем подробности
        _report_failure(exc)
        code = 3
    sys.exit(code)
