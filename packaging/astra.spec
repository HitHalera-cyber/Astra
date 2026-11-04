# Сборка Astra в папку программы (PyInstaller, режим onedir).
# Запуск из корня репозитория:  pyinstaller packaging/astra.spec --noconfirm
# Результат: dist/Astra/Astra.exe (Windows) или dist/Astra/Astra (Linux).

import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent

datas, binaries, hiddenimports = [], [], []
# ядро NASA CEA: расширение Cython, библиотека Fortran и базы thermo.lib / trans.lib
for pkg in ("cea", "astra"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
# PyQtGraph: без примеров, OpenGL и Jupyter (импорт примеров при сборке запускает Qt)
SKIP = ("pyqtgraph.examples", "pyqtgraph.opengl", "pyqtgraph.jupyter")
datas += collect_data_files("pyqtgraph", excludes=["**/examples/**"])
hiddenimports += collect_submodules("pyqtgraph", filter=lambda m: not m.startswith(SKIP))
hiddenimports += collect_submodules("openpyxl")

# Visual C++ 2015–2022 (vcruntime140, vcruntime140_1, msvcp140): кладём в _internal явно,
# иначе на компьютере без Visual C++ Redistributable NumPy и Qt не загружаются, а на машине
# сборки это не видно, потому что там библиотеки есть в System32 (tools/check_bundle.py)
if sys.platform == "win32":
    VC = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
          "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll", "concrt140.dll")
    for name in VC:
        for d in (Path(sys.base_prefix), Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"):
            if (d / name).is_file():
                binaries.append((str(d / name), "."))
                break

# лицензии и уведомления — рядом с программой
for src, dst in (("NOTICE.md", "."), ("third_party/nasa-cea/LICENSE.txt", "licenses/nasa-cea"),
                 ("third_party/nasa-cea/NOTICE.txt", "licenses/nasa-cea")):
    datas.append((str(ROOT / src), dst))

a = Analysis(
    [str(ROOT / "packaging" / "astra_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore",
              "PySide6.Qt3DCore", "PySide6.QtPdf", "pyqtgraph.examples", "pyqtgraph.opengl", "pyqtgraph.jupyter", "tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
# лишнее для оконной программы: QML/Quick, 3D, веб, переводы Qt, кроме русского
DROP = ("Qt6Quick", "Qt6Qml", "Qt63D", "Qt6WebEngine", "Qt6Pdf", "Qt6VirtualKeyboard", "Qt6Multimedia",
        "qml/", "qml\\")


def keep(entry):
    name = entry[0].replace("\\", "/")
    if any(d.replace("\\", "/") in name for d in DROP):
        return False
    if "/translations/" in name and name.endswith(".qm"):
        return name.rsplit("/", 1)[-1].endswith("_ru.qm")
    return True


a.binaries = [e for e in a.binaries if keep(e)]
a.datas = [e for e in a.datas if keep(e)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Astra",
    console=False,          # оконная программа; --selftest пишет отчёт в файл
    icon=str(ROOT / "packaging" / "astra.ico"),   # tools/make_icon.py
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Astra", upx=False)
