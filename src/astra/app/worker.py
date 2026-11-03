"""Выполнение расчёта в фоновом потоке, чтобы интерфейс не замирал."""

from __future__ import annotations

import copy

from PySide6.QtCore import QThread, Signal

from astra.core import AstraError
from astra.projects import Project
from astra.projects.run import run_project


class CalcThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)   # снимок исходных данных на момент запуска

    def run(self) -> None:
        try:
            self.succeeded.emit(run_project(self.project))
        except AstraError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # ошибка, не предусмотренная адаптером, показывается как есть
            self.failed.emit(f"Непредвиденная ошибка: {exc!r}")
