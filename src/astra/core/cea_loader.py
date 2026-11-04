"""Загрузка ядра NASA CEA с базами thermo.lib и trans.lib.

Ядро (Fortran) открывает файлы баз по пути из байтов в кодировке ANSI. В Windows путь
с русскими буквами (например, программа установлена в профиль пользователя с русским
именем) ядро не открывает: «Invalid path; thermo.lib not found». Поэтому в Windows,
если путь к базам не латинский, ядру передаётся короткий путь 8.3, а если его нет —
копия баз в общей папке с латинским путём (C:\\ProgramData\\Astra\\cea-<версия>).
Содержимое баз не меняется.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

FILES = ("thermo.lib", "trans.lib")


def _short_path(path: Path) -> str | None:
    import ctypes

    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
    return buf.value if 0 < n < len(buf) else None


def _ascii_copy(src: Path, version: str) -> str | None:
    bases = [os.environ.get("ProgramData"), os.environ.get("PUBLIC"), tempfile.gettempdir(),
             os.environ.get("SystemDrive", "C:") + "\\"]
    for base in bases:
        if not base or not base.isascii():
            continue
        target = Path(base) / "Astra" / f"cea-{version}"
        try:
            target.mkdir(parents=True, exist_ok=True)
            for name in FILES:
                s, d = src / name, target / name
                if not d.is_file() or d.stat().st_size != s.stat().st_size:
                    tmp = d.with_suffix(".tmp")
                    shutil.copyfile(s, tmp)
                    os.replace(tmp, d)
            return str(target)
        except OSError:
            continue
    return None


def data_dir(cea_file: str, version: str, windows: bool | None = None) -> str:
    """Папка с thermo.lib и trans.lib, путь к которой ядро сможет открыть."""
    src = Path(cea_file).parent / "data"
    windows = os.name == "nt" if windows is None else windows
    if not windows or str(src).isascii():
        return str(src)
    short = _short_path(src)
    if short and short.isascii() and all((Path(short) / n).is_file() for n in FILES):
        return short
    return _ascii_copy(src, version) or str(src)


def load():
    """Импорт пакета `cea` и инициализация ядра с базами по безопасному пути."""
    previous = os.environ.get("CEA_SKIP_INIT")
    os.environ["CEA_SKIP_INIT"] = "1"   # пакет сам инициализирует ядро при импорте
    try:
        import cea
    finally:
        if previous is None:
            os.environ.pop("CEA_SKIP_INIT", None)
        else:
            os.environ["CEA_SKIP_INIT"] = previous
    if not cea.is_initialized():
        cea.init(data_dir(cea.__file__, cea.__version__))
    return cea
