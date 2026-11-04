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
    if sys.platform == "win32":
        try:
            lines += _windows_probe(base)
        except Exception as e:  # диагностика не должна мешать сохранению отчёта
            lines.append(f"Проверка библиотек не выполнена: {e!r}")
    return "\n".join(lines) + "\n"


def _windows_probe(base) -> list[str]:
    """Сведения о системе и поочерёдная загрузка библиотек NumPy: какая из них не запускается."""
    import ctypes
    from ctypes import wintypes
    import winreg

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.LoadLibraryExW.argtypes = (wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD)
    k32.GetModuleHandleW.restype = wintypes.HMODULE
    k32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    k32.GetModuleFileNameW.argtypes = (wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD)
    out = [""]
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        name = winreg.QueryValueEx(key, "ProductName")[0]
        build = winreg.QueryValueEx(key, "CurrentBuild")[0]
        out.append(f"Система: {name}, сборка {build}")
    except OSError:
        pass
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        out.append(f"Процессор: {winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()}")
    except OSError:
        pass

    class MEM(ctypes.Structure):
        _fields_ = [("len", wintypes.DWORD), ("load", wintypes.DWORD)] + [
            (n, ctypes.c_ulonglong) for n in ("phys", "phys_free", "commit", "commit_free", "virt", "virt_free", "ext")]

    m = MEM()
    m.len = ctypes.sizeof(MEM)
    if k32.GlobalMemoryStatusEx(ctypes.byref(m)):
        gb = 1024 ** 3
        out.append(f"Память: {m.phys / gb:.1f} ГБ, свободно {m.phys_free / gb:.1f} ГБ; "
                   f"доступно с подкачкой {m.commit_free / gb:.1f} из {m.commit / gb:.1f} ГБ")

    def where(name: str) -> str:
        h = k32.GetModuleHandleW(name)
        if not h:
            return "не загружена"
        buf = ctypes.create_unicode_buffer(1024)
        k32.GetModuleFileNameW(h, buf, 1024)
        return buf.value

    out.append("Поочерёдная загрузка библиотек (0 — успешно):")
    order = [base / "vcruntime140.dll", base / "vcruntime140_1.dll", base / "msvcp140.dll"]
    libs = base / "numpy.libs"
    if libs.is_dir():
        order += sorted(libs.glob("msvcp140*.dll")) + sorted(libs.glob("*openblas*.dll"))
    order += sorted((base / "numpy" / "_core").glob("_multiarray_umath*.pyd"))
    for path in order:
        if not path.is_file():
            out.append(f"  {path.name}: нет файла")
            continue
        h = k32.LoadLibraryExW(str(path), None, 0x00000008)  # LOAD_WITH_ALTERED_SEARCH_PATH
        err = 0 if h else ctypes.get_last_error()
        out.append(f"  {path.name}: {err}" + (f" ({ctypes.FormatError(err).strip()})" if err else ""))
    for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "ucrtbase.dll"):
        out.append(f"  загружена {name}: {where(name)}")

    # все библиотеки в процессе: посторонние (антивирус, оверлеи) видны по пути
    psapi = ctypes.WinDLL("psapi")
    mods = (wintypes.HMODULE * 2048)()
    need = wintypes.DWORD()
    proc = k32.GetCurrentProcess()
    psapi.EnumProcessModules.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    if psapi.EnumProcessModules(proc, mods, ctypes.sizeof(mods), ctypes.byref(need)):
        names = []
        buf = ctypes.create_unicode_buffer(1024)
        for h in mods[: need.value // ctypes.sizeof(wintypes.HMODULE)]:
            k32.GetModuleFileNameW(h, buf, 1024)
            low = buf.value.lower()
            if str(base).lower() not in low and "\\windows\\system32\\" not in low:
                names.append(buf.value)
        out.append("Посторонние библиотеки в процессе: " + (", ".join(names) if names else "нет"))
    return out


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
