"""Главное окно: звёздный фон, верхняя строка с разделами, маршрут расчёта и страницы разделов."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
                               QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from astra.core import NozzleResult, core_version, q
from astra.core.notation import EQUILIBRIUM_PROBLEMS

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
from .space import RouteBar, SpaceBackground, app_icon, app_icon_pixmap, section_icon, ui_assets
from .state import AppState
from .theme import colors, stylesheet
from .widgets import fmt

# ключ, полное название раздела, короткая подпись в верхней строке
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
SHORT = {"home": "Главная", "propellant": "Топливо", "conditions": "Условия", "thermo": "Расчёт",
         "parametric": "Серии", "nozzle": "Сопло", "isp": "Iуд", "plots": "Графики", "tables": "Таблицы",
         "database": "Вещества", "projects": "Проекты", "settings": "Настройки"}
FULL_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
# раздел, который подсвечивается на маршруте, когда открыт раздел вне маршрута
ROUTE_ALIAS = {"plots": "tables"}


class MainWindow(QMainWindow):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.theme = "dark"
        self.setWindowTitle("Astra — термодинамические расчёты на базе NASA CEA")
        self.setWindowIcon(app_icon())
        self.resize(1360, 900)
        self.setMinimumSize(1100, 700)

        self.background = SpaceBackground()
        outer = QVBoxLayout(self.background)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # верхняя строка: значок, название, проект, тема, сохранение, расчёт
        top = QWidget()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 12, 24, 2)
        mark = QLabel()
        mark.setPixmap(app_icon_pixmap(64).scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))
        logo = QLabel("ASTRA")
        logo.setObjectName("Logo")
        self.project_label = QLabel("")
        self.project_label.setObjectName("ProjectName")
        tl.addWidget(mark)
        tl.addSpacing(6)
        tl.addWidget(logo)
        tl.addWidget(self.project_label, 1)
        self.theme_btn = QPushButton("")
        self.theme_btn.setObjectName("TopButton")
        self.theme_btn.clicked.connect(self.toggle_theme)
        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("TopButton")
        save_btn.setToolTip("Сохранить проект (Ctrl+S)")
        save_btn.clicked.connect(lambda: self.state.save())
        self.run_btn = QPushButton("▶  Рассчитать   F5")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setToolTip("Термодинамический расчёт ядром NASA CEA по исходным данным проекта")
        self.run_btn.clicked.connect(self.run_calc)
        for b in (self.theme_btn, save_btn, self.run_btn):
            tl.addWidget(b)
        outer.addWidget(top)

        # строка разделов
        nav_row = QWidget()
        nav_row.setObjectName("NavRow")
        nl = QHBoxLayout(nav_row)
        nl.setContentsMargins(18, 0, 18, 0)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFlow(QListView.Flow.LeftToRight)
        self.nav.setWrapping(False)
        self.nav.setIconSize(QSize(16, 16))
        self.nav.setFixedHeight(40)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        nl.addWidget(self.nav)
        outer.addWidget(nav_row)

        # маршрут расчёта
        self.route = RouteBar()
        self.route.step_clicked.connect(self.go_to)
        route_box = QWidget()
        rl = QHBoxLayout(route_box)
        rl.setContentsMargins(26, 4, 26, 0)
        rl.addWidget(self.route)
        self.route_box = route_box
        outer.addWidget(route_box)

        root = QWidget()
        root.setObjectName("Root")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        outer.addWidget(root, 1)
        self.setCentralWidget(self.background)

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
            "settings": SettingsPage(state, self.apply_theme, self.set_route_visible),
        }
        for key, name in SECTIONS:
            page = built[key]
            self.pages[key] = page
            self.stack.addWidget(page)
            item = QListWidgetItem(SHORT[key])
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setData(FULL_NAME_ROLE, name)
            item.setToolTip(name)
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._switch)
        self.nav.setCurrentRow(0)

        save = QAction("Сохранить", self)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(lambda: self.state.save())
        self.addAction(save)
        run = QAction("Рассчитать", self)
        run.setShortcut(QKeySequence("F5"))
        run.triggered.connect(self.run_calc)
        self.addAction(run)

        state.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
        for sig in (state.project_changed, state.data_changed, state.saved):
            sig.connect(self._title)
        for sig in (state.project_changed, state.data_changed, state.result_ready, state.study_ready,
                    state.nozzle_ready, state.isp_ready):
            sig.connect(self._update_route)
        self._title()
        settings = QSettings("Astra", "Astra")
        self.set_route_visible(settings.value("show_route", True, type=bool))
        self.apply_theme(settings.value("theme", "dark"))
        self.statusBar().showMessage(f"Готово · ядро NASA CEA {core_version()} · Ctrl+S — сохранить, F5 — рассчитать")

    # ------------------------------------------------------------ навигация
    def _switch(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()
        self._update_route()

    def go_to(self, key: str) -> None:
        self.nav.setCurrentRow([k for k, _ in SECTIONS].index(key))

    def current_key(self) -> str:
        return SECTIONS[max(0, self.nav.currentRow())][0]

    def run_calc(self) -> None:
        self.go_to("thermo")
        self.pages["thermo"].run()

    def set_route_visible(self, on: bool) -> None:
        self.route_box.setVisible(bool(on))

    def route_steps(self) -> list[dict]:
        """Шаги маршрута по текущему проекту и полученным результатам (ничего не рассчитывается)."""
        st = self.state
        p = st.project
        c = p.conditions
        comps = [x.name for x in p.components]
        rocket = c.calc == "rocket"
        if p.components and all(x.role == "mixture" for x in p.components):
            ratio = "смесь"
        else:
            ratio = f"{'Kм' if c.ratio_kind == 'Km' else 'α'} {fmt(c.ratio_value, 4)}"
        if rocket:
            cond = f"Pк {fmt(q('pk').to_display(c.pk), 4)} МПа · {ratio}"
        elif c.calc in EQUILIBRIUM_PROBLEMS:
            cond = f"{c.calc} · {ratio}"
        else:
            cond = {"shock": "ударная волна", "detonation": "детонация"}.get(c.calc, c.calc) + f" · {ratio}"
        r = st.last_result
        if r is None:
            calc = "не выполнялся"
        elif isinstance(r, NozzleResult):
            try:
                ch = r.chamber
                calc = f"Tк {fmt(ch['t'], 4)} К · k {fmt(ch['k'], 4)}"
            except LookupError:
                calc = "выполнен"
        else:
            calc = "выполнен"
        eps = " · ".join(fmt(e, 3) for e in c.eps) if c.eps else "по Pк/P"
        any_result = any(x is not None for x in (st.last_result, st.last_study, st.last_nozzle, st.last_isp))
        return [
            {"key": "propellant", "title": "Топливо", "sub": " + ".join(comps) or "не задано",
             "done": bool(comps), "tip": "Топливо и окислитель: компоненты, доли, начальные температуры"},
            {"key": "conditions", "title": "Условия", "sub": cond, "done": bool(comps),
             "tip": "Исходные условия: вид расчёта, Kм или α, давление, сопло"},
            {"key": "thermo", "title": "Расчёт", "sub": calc,
             "done": r is not None and getattr(r, "converged", False),
             "tip": "Термодинамический расчёт ядром NASA CEA"},
            {"key": "nozzle", "title": "Сопло", "sub": f"ε {eps}" if rocket else "для камеры и сопла",
             "done": st.last_nozzle is not None, "tip": "Исследование сопла при неизменной камере"},
            {"key": "parametric", "title": "Серии", "sub": "Kм · α · Pк · Tк · i",
             "done": st.last_study is not None, "tip": "Параметрические исследования"},
            {"key": "isp", "title": "Iуд", "sub": "Kм · ε · Pн", "done": st.last_isp is not None,
             "tip": "Анализ удельного импульса"},
            {"key": "tables", "title": "Результаты", "sub": "графики · таблицы · отчёт", "done": any_result,
             "tip": "Таблицы результатов, графики и отчёт"},
        ]

    def _update_route(self, *_):
        key = self.current_key()
        self.route.set_steps(self.route_steps(), ROUTE_ALIAS.get(key, key))

    # ------------------------------------------------------------ оформление
    def apply_theme(self, name: str) -> None:
        name = name if name in ("dark", "light") else "dark"
        self.theme = name
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(name, ui_assets(name)))
        c = colors(name)
        self.background.set_theme(name)
        self.route.set_theme(name)
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            it.setIcon(section_icon(it.data(Qt.ItemDataRole.UserRole), c["accent"]))
        self.theme_btn.setText("Светлая тема" if name == "dark" else "Тёмная тема")
        self.theme_btn.setToolTip("Переключить оформление: «Глубокий космос» или «Орбита днём»")
        for page in getattr(self, "pages", {}).values():
            if hasattr(page, "apply_theme"):
                page.apply_theme(name)

    def toggle_theme(self) -> None:
        name = "light" if self.theme == "dark" else "dark"
        QSettings("Astra", "Astra").setValue("theme", name)
        self.apply_theme(name)

    def _title(self) -> None:
        p = self.state.project
        mark = " •" if self.state.dirty else ""
        self.setWindowTitle(f"{p.name}{mark} — Astra")
        self.project_label.setText(f"{p.name}{mark}")

    def closeEvent(self, event) -> None:
        if self.state.dirty and self.state.project.id is not None:
            self.state.save(quiet=True)
        super().closeEvent(event)
