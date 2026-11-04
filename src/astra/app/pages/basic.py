"""Разделы «Главная», «Настройки» и разделы следующих этапов."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton

from astra import __version__
from astra.core import QUANTITIES, core_version

from ..theme import THEME_NAMES
from ..widgets import Page, card, fmt, make_table, ro_item


class HomePage(Page):
    title = "Главная"
    hint = ("Astra — комплекс термодинамических расчётов на базе вычислительного ядра NASA CEA. "
            "Все результаты рассчитываются оригинальным ядром; оболочка задаёт исходные данные и "
            "представляет результаты в отечественной системе обозначений.")

    def __init__(self, state, go_to, parent=None):
        super().__init__(parent)
        self.state = state
        frame, lay = card("Текущий проект")
        self.info = QLabel("")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        row = QHBoxLayout()
        b_new = QPushButton("Новый проект")
        b_ex = QPushButton("Пример: H2(L) + O2(L)")
        b_calc = QPushButton("Перейти к расчёту")
        b_calc.setObjectName("Primary")
        b_new.clicked.connect(lambda: state.new_project())
        b_ex.clicked.connect(lambda: state.new_project(example=True))
        b_calc.clicked.connect(lambda: go_to("thermo"))
        for b in (b_new, b_ex, b_calc):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.body.addWidget(frame)

        frame, lay = card("Порядок работы")
        steps = QLabel(
            "1. «Топливо и окислитель» — выбрать компоненты из базы NASA CEA, задать доли и начальные температуры.<br>"
            "2. «Исходные условия» — тип расчёта, Kм или α, Pк, параметры сопла и модель течения.<br>"
            "3. «Термодинамический расчёт» — запустить ядро, получить параметры и состав продуктов.<br>"
            "4. «Проекты» — сохранение, копии, журнал расчётов.")
        steps.setWordWrap(True)
        lay.addWidget(steps)
        self.body.addWidget(frame)

        frame, lay = card("Вычислительное ядро")
        lay.addWidget(QLabel(
            f"NASA CEA {core_version()} (Apache 2.0, © 2025 United States Government as represented by the "
            f"Administrator of NASA). Ядро используется без изменений. Astra {__version__}."))
        self.body.addWidget(frame)
        self.body.addStretch(1)
        state.project_changed.connect(self.refresh)
        state.data_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        p = self.state.project
        comps = ", ".join(f"{c.name} ({'горючее' if c.role == 'fuel' else 'окислитель'})" for c in p.components)
        self.info.setText(f"<b>{p.name}</b><br>Компоненты: {comps or 'не заданы'}")


class SettingsPage(Page):
    title = "Настройки"
    hint = "Оформление и поведение программы. Настройки сохраняются для текущего пользователя Windows."

    def __init__(self, state, apply_theme, show_route=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.settings = QSettings("Astra", "Astra")
        box = QGroupBox("Интерфейс")
        f = QFormLayout(box)
        self.theme = QComboBox()
        for key, name in THEME_NAMES.items():
            self.theme.addItem(name, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self.settings.value("theme", "dark"))))
        self.theme.currentIndexChanged.connect(lambda: self._theme(apply_theme))
        f.addRow("Тема оформления:", self.theme)
        self.autosave = QCheckBox("Автоматически сохранять исходные данные проекта")
        self.autosave.setChecked(self.settings.value("autosave", True, type=bool))
        self.autosave.toggled.connect(self._autosave)
        f.addRow(self.autosave)
        self.show_route = QCheckBox("Показывать маршрут расчёта под строкой разделов")
        self.show_route.setChecked(self.settings.value("show_route", True, type=bool))
        self.show_route.toggled.connect(lambda on: self._route(on, show_route))
        f.addRow(self.show_route)
        f.addRow("Файл проектов:", QLabel(str(state.store.path)))
        self.body.addWidget(box)

        frame, lay = card("Система обозначений")
        t = make_table(["Обозначение", "Наименование", "Единица", "Физический смысл"])
        t.setRowCount(len(QUANTITIES))
        for r, qt in enumerate(QUANTITIES.values()):
            for c, text in enumerate([qt.symbol, qt.name, qt.unit or "—", qt.meaning]):
                t.setItem(r, c, ro_item(text))
        t.setMinimumHeight(420)
        lay.addWidget(t)
        self.body.addWidget(frame)
        self.body.addStretch(1)

    def _theme(self, apply_theme) -> None:
        key = self.theme.currentData()
        self.settings.setValue("theme", key)
        apply_theme(key)

    def apply_theme(self, name: str) -> None:
        """Синхронизировать список тем, если тема переключена кнопкой в верхней строке."""
        i = self.theme.findData(name)
        if i >= 0 and i != self.theme.currentIndex():
            self.theme.blockSignals(True)
            self.theme.setCurrentIndex(i)
            self.theme.blockSignals(False)

    def _route(self, on: bool, show_route) -> None:
        self.settings.setValue("show_route", on)
        if show_route is not None:
            show_route(on)

    def _autosave(self, on: bool) -> None:
        self.settings.setValue("autosave", on)
        self.state.autosave = on


class PlannedPage(Page):
    """Раздел следующего этапа. Кнопок без действия здесь нет — только описание."""

    def __init__(self, title: str, stage: int, what: str, parent=None):
        self.title = title
        self.hint = ""
        super().__init__(parent)
        frame, lay = card(f"Раздел будет реализован на этапе {stage}")
        lbl = QLabel(what)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.body.addWidget(frame)
        self.body.addStretch(1)
