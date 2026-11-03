"""Состояние приложения: текущий проект, хранилище, последний результат."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from astra.projects import Project, ProjectStore


class AppState(QObject):
    project_changed = Signal()       # открыт или создан другой проект
    data_changed = Signal()          # изменены исходные данные текущего проекта
    saved = Signal()
    result_ready = Signal(object)    # EquilibriumResult | NozzleResult
    message = Signal(str)            # сообщение для строки состояния

    def __init__(self, store: ProjectStore, autosave: bool = True, autosave_ms: int = 3000):
        super().__init__()
        self.store = store
        self.project = Project.example()
        self.last_result = None
        self.dirty = False
        self.autosave = autosave
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(autosave_ms)
        self._timer.timeout.connect(self._autosave)

    # --- изменения
    def touch(self) -> None:
        self.dirty = True
        self.data_changed.emit()
        if self.autosave and self.project.id is not None:
            self._timer.start()

    def _autosave(self) -> None:
        if self.dirty and self.project.id is not None:
            self.save(quiet=True)

    # --- проекты
    def set_project(self, project: Project) -> None:
        self.project = project
        self.last_result = None
        self.dirty = project.id is None
        self.project_changed.emit()

    def new_project(self, example: bool = False) -> None:
        p = Project.example() if example else Project()
        self.set_project(self.store.save(p))
        self.message.emit(f"Создан проект «{p.name}».")

    def open_project(self, project_id: int) -> None:
        self.set_project(self.store.load(project_id))
        self.message.emit(f"Открыт проект «{self.project.name}».")

    def save(self, quiet: bool = False) -> None:
        self.store.save(self.project)
        self.dirty = False
        self.saved.emit()
        if not quiet:
            self.message.emit(f"Проект «{self.project.name}» сохранён.")
        else:
            self.message.emit("Автосохранение выполнено.")
