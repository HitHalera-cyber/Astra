"""Раздел «Проекты»: создание, открытие, дублирование, удаление и журнал расчётов."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QPushButton, QLabel

from ..widgets import Page, card, make_table, ro_item


class ProjectsPage(Page):
    title = "Проекты"
    hint = ("Проекты хранятся в базе SQLite. Исходные данные сохраняются автоматически; "
            "каждый расчёт попадает в журнал вместе с исходными данными и версией ядра.")

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        frame, lay = card("Текущий проект")
        row = QHBoxLayout()
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._rename)
        row.addWidget(QLabel("Название:"))
        row.addWidget(self.name, 1)
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(lambda: self.state.save())
        row.addWidget(self.save_btn)
        lay.addLayout(row)
        self.body.addWidget(frame)

        frame, lay = card("Все проекты")
        row = QHBoxLayout()
        self.new_btn = QPushButton("Новый")
        self.example_btn = QPushButton("Новый из примера")
        self.open_btn = QPushButton("Открыть")
        self.dup_btn = QPushButton("Дублировать")
        self.del_btn = QPushButton("Удалить")
        self.new_btn.clicked.connect(lambda: self.state.new_project())
        self.example_btn.clicked.connect(lambda: self.state.new_project(example=True))
        self.open_btn.clicked.connect(self._open)
        self.dup_btn.clicked.connect(self._duplicate)
        self.del_btn.clicked.connect(self._delete)
        for b in (self.new_btn, self.example_btn, self.open_btn, self.dup_btn, self.del_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.list = make_table(["№", "Название", "Создан", "Изменён"])
        self.list.setMinimumHeight(200)
        self.list.doubleClicked.connect(lambda *_: self._open())
        lay.addWidget(self.list)
        self.body.addWidget(frame)

        frame, lay = card("Журнал расчётов текущего проекта")
        self.log = make_table(["Время", "Расчёт", "Сходимость", "Сообщение", "Ядро"])
        self.log.setMinimumHeight(200)
        lay.addWidget(self.log)
        self.body.addWidget(frame)
        self.body.addStretch(1)

        state.project_changed.connect(self.refresh)
        state.saved.connect(self.refresh)
        state.result_ready.connect(lambda _r: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        p = self.state.project
        self.name.setText(p.name)
        rows = self.state.store.list()
        self.list.setRowCount(len(rows))
        for r, (pid, name, created, modified) in enumerate(rows):
            for c, text in enumerate([str(pid), name, created.replace("T", " "), modified.replace("T", " ")]):
                self.list.setItem(r, c, ro_item(text))
        recs = self.state.store.calculations(p.id) if p.id is not None else []
        self.log.setRowCount(len(recs))
        for r, rec in enumerate(recs):
            kind = {"rocket": "Камера и сопло", "shock": "Ударная волна",
                    "detonation": "Детонация"}.get(rec.kind, rec.kind)
            for c, text in enumerate([rec.timestamp.replace("T", " "), kind, "да" if rec.converged else "нет",
                                      rec.message, rec.core_version]):
                self.log.setItem(r, c, ro_item(text))

    def _selected_id(self) -> int | None:
        r = self.list.currentRow()
        it = self.list.item(r, 0) if r >= 0 else None
        return int(it.text()) if it else None

    def _rename(self) -> None:
        text = self.name.text().strip()
        if text and text != self.state.project.name:
            self.state.project.name = text
            self.state.touch()
            self.state.save()

    def _open(self) -> None:
        pid = self._selected_id()
        if pid is not None:
            if self.state.dirty and self.state.project.id is not None:
                self.state.save(quiet=True)
            self.state.open_project(pid)

    def _duplicate(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        name, ok = QInputDialog.getText(self, "Дублировать проект", "Название копии:",
                                        text=self.state.store.load(pid).name + " (копия)")
        if ok:
            self.state.store.duplicate(pid, name.strip() or None)
            self.refresh()

    def _delete(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        p = self.state.store.load(pid)
        if QMessageBox.question(self, "Удалить проект",
                                f"Удалить проект «{p.name}» вместе с журналом расчётов? Действие необратимо.") \
                != QMessageBox.StandardButton.Yes:
            return
        self.state.store.delete(pid)
        if pid == self.state.project.id:
            rows = self.state.store.list()
            if rows:
                self.state.open_project(rows[0][0])
            else:
                self.state.new_project()
        self.refresh()
