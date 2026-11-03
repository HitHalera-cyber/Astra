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


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Astra")
    app.setOrganizationName("Astra")
    win = create_window()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
