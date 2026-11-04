"""Запуск приложения: python -m astra"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication

from astra.projects import ProjectStore

from .main_window import MainWindow
from .state import AppState


def default_store_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(base or Path.home() / ".astra") / "projects.sqlite"


def create_window(store_path: Path | None = None) -> MainWindow:
    store = ProjectStore(store_path or default_store_path())
    settings = QSettings("Astra", "Astra")
    state = AppState(store, autosave=settings.value("autosave", True, type=bool))
    rows = store.list()
    if rows:
        state.open_project(rows[0][0])
    else:
        state.new_project(example=True)
    return MainWindow(state)


def install_russian_qt(app) -> bool:
    """Русские стандартные диалоги Qt (выбор файла, кнопки «Отмена», «Открыть»…)."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ok = False
    for name in ("qtbase_ru", "qt_ru"):
        tr = QTranslator(app)
        if tr.load(name, path):
            app.installTranslator(tr)
            ok = True
    QLocale.setDefault(QLocale(QLocale.Language.Russian, QLocale.Country.Russia))
    return ok


def main(argv: list[str] | None = None) -> int:
    import multiprocessing
    multiprocessing.freeze_support()
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--selftest":
        from astra.selftest import main as selftest
        return selftest(argv[1] if len(argv) > 1 else None)
    if argv and argv[0] in ("--version", "-V"):
        from astra import __version__
        from astra.core import core_version
        text = f"Astra {__version__}, ядро NASA CEA {core_version()}\n"
        if sys.stdout is not None:
            sys.stdout.write(text)
        return 0
    app = QApplication.instance() or QApplication(sys.argv)
    install_russian_qt(app)
    app.setApplicationName("Astra")
    app.setOrganizationName("Astra")
    win = create_window()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
