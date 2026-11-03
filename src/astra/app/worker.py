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


class StudyThread(QThread):
    """Серия расчётов параметрического исследования с прогрессом и отменой."""

    progress = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        from astra.projects.study import run_study
        try:
            res = run_study(self.project, progress=lambda d, t: self.progress.emit(d, t),
                            cancelled=lambda: self._cancel)
            self.succeeded.emit(res)
        except AstraError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Непредвиденная ошибка: {exc!r}")


class JobThread(QThread):
    """Произвольное исследование проекта: job(project, progress, cancelled) → результат."""

    progress = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, project: Project, job, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.job = job
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            res = self.job(self.project, lambda d, t: self.progress.emit(d, t), lambda: self._cancel)
            self.succeeded.emit(res)
        except AstraError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Непредвиденная ошибка: {exc!r}")
