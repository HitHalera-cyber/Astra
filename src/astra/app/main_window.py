"""Главное окно: боковая навигация и разделы."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QStackedWidget, QVBoxLayout, QWidget)

from .pages.basic import HomePage, SettingsPage
from .pages.conditions import ConditionsPage
from .pages.database import DatabasePage
from .pages.isp import IspPage
from .pages.nozzle import NozzlePage
from .pages.parametric import ParametricPage
from .pages.plots import PlotsPage
from .pages.projects import ProjectsPage
from .pages.propellant import PropellantPage
from .pages.tables import TablesPage
from .pages.thermo import ThermoPage
from .state import AppState
from .theme import stylesheet

SECTIONS = [
    ("home", "Главная"),
    ("propellant", "Топливо и окислитель"),
    ("conditions", "Исходные условия"),
    ("thermo", "Термодинамический расчёт"),
    ("parametric", "Параметрические исследования"),
    ("nozzle", "Исследование сопла"),
    ("isp", "Удельный импульс"),
    ("plots", "Графики"),
    ("tables", "Таблицы результатов"),
    ("database", "База веществ"),
    ("projects", "Проекты"),
    ("settings", "Настройки"),
]


class MainWindow(QMainWindow):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setWindowTitle("Astra — термодинамические расчёты на базе NASA CEA")
        self.resize(1320, 840)

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(272)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 8)
        title = QLabel("Astra")
        title.setObjectName("AppTitle")
        sub = QLabel("на базе NASA CEA")
        sub.setObjectName("AppSubtitle")
        sl.addWidget(title)
        sl.addWidget(sub)
        self.nav = QListWidget()
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sl.addWidget(self.nav, 1)
        lay.addWidget(side)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.pages: dict[str, QWidget] = {}
        propellant = PropellantPage(state)
        plots = PlotsPage(state)
        built = {
            "home": HomePage(state, self.go_to),
            "propellant": propellant,
            "conditions": ConditionsPage(state),
            "thermo": ThermoPage(state),
            "parametric": ParametricPage(state),
            "nozzle": NozzlePage(state),
            "isp": IspPage(state),
            "plots": plots,
            "tables": TablesPage(state, plots.plot_image),
            "database": DatabasePage(state, propellant),
            "projects": ProjectsPage(state),
            "settings": SettingsPage(state, self.apply_theme),
        }
        for key, name in SECTIONS:
            page = built[key]
            self.pages[key] = page
            self.stack.addWidget(page)
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._switch)
        self.nav.setCurrentRow(0)

        save = QAction("Сохранить", self)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(lambda: self.state.save())
        self.addAction(save)
        run = QAction("Рассчитать", self)
        run.setShortcut(QKeySequence("F5"))
        run.triggered.connect(lambda: (self.go_to("thermo"), self.pages["thermo"].run()))
        self.addAction(run)

        state.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
        state.project_changed.connect(self._title)
        state.data_changed.connect(self._title)
        state.saved.connect(self._title)
        self._title()
        self.apply_theme(QSettings("Astra", "Astra").value("theme", "dark"))
        self.statusBar().showMessage("Готово. Ctrl+S — сохранить проект, F5 — рассчитать.")

    def _switch(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    def go_to(self, key: str) -> None:
        self.nav.setCurrentRow([k for k, _ in SECTIONS].index(key))

    def apply_theme(self, name: str) -> None:
        name = name if name in ("dark", "light") else "dark"
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(name))
        if "plots" in getattr(self, "pages", {}):
            self.pages["plots"].apply_theme(name)

    def _title(self) -> None:
        p = self.state.project
        mark = " •" if self.state.dirty else ""
        self.setWindowTitle(f"{p.name}{mark} — Astra")

    def closeEvent(self, event) -> None:
        if self.state.dirty and self.state.project.id is not None:
            self.state.save(quiet=True)
        super().closeEvent(event)
