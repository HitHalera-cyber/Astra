"""Раздел «Параметрические исследования»."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from astra.core import InputError, WAVE_PROBLEMS, core_version, q
from astra.core.notation import EQUILIBRIUM_PROBLEMS
from astra.projects import AxisSpec
from astra.projects import study as st

from ..widgets import Page, card, fmt, make_table, parse_number, ro_item
from ..worker import StudyThread

MAX_AXES = 4

# величины, которые можно вывести в таблицу серии, и выбранные по умолчанию
ROCKET_OUT = ["t", "p", "k", "mu", "mu_c", "i", "s", "w", "M", "eps", "c_star", "kt", "isp", "isp_vac", "isp_amb",
              "kt_n", "f_kr", "f_a", "thrust", "rho", "cp", "a", "pk_p"]
ROCKET_DEFAULT = ["t", "k", "mu", "c_star", "isp", "isp_vac"]
EQ_OUT = ["t", "p", "rho", "v", "i", "u", "s", "g", "cp", "cp_fr", "cv", "k", "mu", "mu_c", "a"]
EQ_DEFAULT = ["t", "p", "rho", "k", "mu"]


class AxisRow(QWidget):
    """Одна ось: величина, способ задания и значения (в единицах отображения)."""

    def __init__(self, page: "ParametricPage", spec: AxisSpec, parent=None):
        super().__init__(parent)
        self.page = page
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.key = QComboBox()
        self.mode = QComboBox()
        for k, text in st.MODES.items():
            self.mode.addItem(text, k)
        self.start = QLineEdit()
        self.stop = QLineEdit()
        self.step = QLineEdit()
        self.count = QSpinBox()
        self.count.setRange(1, 10000)
        self.log = QCheckBox("лог. шкала")
        self.unit = QLabel("")
        self.unit.setMinimumWidth(70)
        self.remove = QPushButton("Удалить")
        for w, ph in ((self.start, "от"), (self.stop, "до"), (self.step, "шаг")):
            w.setPlaceholderText(ph)
            w.setMaximumWidth(130)
        self.labels = {name: QLabel(name) for name in ("от", "до", "шаг", "точек")}
        lay.addWidget(self.key, 3)
        lay.addWidget(self.mode, 2)
        lay.addWidget(self.labels["от"])
        lay.addWidget(self.start, 1)
        lay.addWidget(self.labels["до"])
        lay.addWidget(self.stop, 1)
        lay.addWidget(self.labels["шаг"])
        lay.addWidget(self.step, 1)
        lay.addWidget(self.labels["точек"])
        lay.addWidget(self.count)
        lay.addWidget(self.log)
        lay.addWidget(self.unit)
        lay.addWidget(self.remove)
        self.set_spec(spec)
        self.key.currentIndexChanged.connect(self._key_changed)
        self.mode.currentIndexChanged.connect(self._changed)
        for w in (self.start, self.stop, self.step):
            w.editingFinished.connect(self._changed)
        self.count.valueChanged.connect(self._changed)
        self.log.toggled.connect(self._changed)
        self.remove.clicked.connect(lambda: page.remove_axis(self))

    def fill_keys(self, keys: list[str], current: str) -> None:
        self.key.blockSignals(True)
        self.key.clear()
        for k in keys:
            self.key.addItem(st.AXIS_TITLES[k], k)
        idx = self.key.findData(current)
        self.key.setCurrentIndex(idx if idx >= 0 else 0)
        self.key.blockSignals(False)

    def set_spec(self, spec: AxisSpec) -> None:
        self._spec_key = spec.key
        qt = q(spec.key)
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(max(0, self.mode.findData(spec.mode)))
        self.mode.blockSignals(False)
        self.start.setText(fmt(qt.to_display(spec.start), 8))
        self.stop.setText(fmt(qt.to_display(spec.stop), 8))
        self.step.setText(fmt(qt.to_display(spec.step), 8))
        self.count.blockSignals(True)
        self.count.setValue(int(spec.count))
        self.count.blockSignals(False)
        self.log.blockSignals(True)
        self.log.setChecked(spec.log)
        self.log.blockSignals(False)
        self._update()

    def spec(self) -> AxisSpec:
        key = self.key.currentData() or self._spec_key
        qt = q(key)
        mode = self.mode.currentData()

        def num(edit: QLineEdit, what: str) -> float:
            try:
                return qt.from_display(parse_number(edit.text()))
            except InputError as exc:
                raise InputError(f"{qt.symbol}, {what}: {exc}") from None

        start = num(self.start, "начальное значение")
        stop = num(self.stop, "конечное значение") if mode != "fixed" else start
        step = num(self.step, "шаг") if mode == "step" else 1.0
        return AxisSpec(key, mode, start, stop, step, self.count.value(), self.log.isChecked())

    def _key_changed(self) -> None:
        key = self.key.currentData()
        if key and key != self._spec_key:
            # новые значения по умолчанию — вокруг текущего значения исходных условий
            self.set_spec(self.page.default_axis(key))
        self._changed()

    def _changed(self) -> None:
        self._update()
        self.page.axes_changed()

    def _update(self) -> None:
        mode = self.mode.currentData()
        key = self.key.currentData() or self._spec_key
        qt = q(key)
        self.unit.setText(qt.unit)
        self.unit.setToolTip(f"{qt.name}. {qt.meaning}")
        ranged = mode != "fixed"
        for w in (self.stop, self.labels["до"]):
            w.setVisible(ranged)
        for w in (self.step, self.labels["шаг"]):
            w.setVisible(mode == "step")
        for w in (self.count, self.labels["точек"], self.log):
            w.setVisible(mode == "count")
        self.labels["от"].setText("от" if ranged else "значение")


class ParametricPage(Page):
    title = "Параметрические исследования"
    hint = ("Серия полных расчётов ядром NASA CEA: исходные условия берутся из раздела «Исходные условия», "
            "варьируются только выбранные величины. Несколько осей дают все сочетания значений. "
            "Точки, в которых ядро не сошлось или исходные данные недопустимы, остаются в таблице "
            "с пометкой и не заменяются ни интерполяцией, ни соседними значениями.")

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.thread: StudyThread | None = None
        self.result: st.StudyResult | None = None
        self._loading = False

        frame, lay = card("Базовые исходные условия")
        self.base = QLabel("")
        self.base.setWordWrap(True)
        lay.addWidget(self.base)
        self.body.addWidget(frame)

        frame, lay = card("Варьируемые величины")
        self.axes_box = QVBoxLayout()
        lay.addLayout(self.axes_box)
        row = QHBoxLayout()
        self.add_axis_btn = QPushButton("Добавить величину")
        self.add_axis_btn.clicked.connect(self.add_axis)
        self.points_label = QLabel("")
        self.points_label.setObjectName("Muted")
        row.addWidget(self.add_axis_btn)
        row.addWidget(self.points_label, 1)
        lay.addLayout(row)
        self.axis_error = QLabel("")
        self.axis_error.setObjectName("Bad")
        self.axis_error.setWordWrap(True)
        lay.addWidget(self.axis_error)
        self.rows: list[AxisRow] = []
        self.body.addWidget(frame)

        frame, lay = card("Расчёт серии")
        row = QHBoxLayout()
        self.run_btn = QPushButton("Рассчитать серию")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        self.workers = QSpinBox()
        self.workers.setRange(0, 64)
        self.workers.setSpecialValueText("авто")
        self.workers.setToolTip("Число параллельных процессов. «Авто»: небольшие серии считаются в одном процессе, "
                                f"начиная с {st.AUTO_PARALLEL_FROM} точек — по числу ядер процессора минус одно.")
        self.workers.valueChanged.connect(self._workers_changed)
        self.progress = QProgressBar()
        self.progress.setFormat("%v из %m")
        row.addWidget(self.run_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(QLabel("процессов:"))
        row.addWidget(self.workers)
        row.addWidget(self.progress, 1)
        lay.addLayout(row)
        self.status = QLabel("Серия ещё не рассчитывалась.")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.body.addWidget(frame)

        frame, lay = card("Результаты серии")
        grid = QGridLayout()
        grid.addWidget(QLabel("Сечение / точка:"), 0, 0)
        self.section = QComboBox()
        self.section.currentIndexChanged.connect(self._section_changed)
        grid.addWidget(self.section, 0, 1)
        grid.addWidget(QLabel("Величины в таблице:"), 1, 0, Qt.AlignmentFlag.AlignTop)
        self.outputs = QListWidget()
        self.outputs.setFlow(QListWidget.Flow.LeftToRight)
        self.outputs.setWrapping(True)
        self.outputs.setMaximumHeight(64)
        self.outputs.itemChanged.connect(lambda *_: self.fill_table())
        grid.addWidget(self.outputs, 1, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.table = make_table(["№"])
        self.table.setMinimumHeight(380)
        lay.addWidget(self.table, 1)
        self.body.addWidget(frame, 1)

        state.project_changed.connect(self.load_project)
        state.data_changed.connect(self.refresh)
        self.load_project()

    # ------------------------------------------------------------ состояние
    def _is_mixture(self) -> bool:
        comps = self.state.project.components
        return bool(comps) and all(c.role == "mixture" for c in comps)

    def allowed(self) -> list[str]:
        return st.available_axes(self.state.project.conditions, self._is_mixture())

    def default_axis(self, key: str) -> AxisSpec:
        c = self.state.project.conditions
        if key == "Km":
            base = c.ratio_value if c.ratio_kind == "Km" else 3.0
            return AxisSpec("Km", "count", base * 0.6, base * 1.4, base * 0.1, 9)
        if key == "alpha":
            return AxisSpec("alpha", "count", 0.5, 1.2, 0.1, 8)
        if key in ("pk", "p"):
            return AxisSpec(key, "count", c.pk / 10, c.pk * 2, c.pk / 10, 6, log=True)
        if key in ("tk", "t"):
            return AxisSpec(key, "step", 1000.0, 4000.0, 500.0, 7)
        if key == "v":
            return AxisSpec("v", "count", c.v / 10, c.v * 10, c.v, 5, log=True)
        if key in ("i", "u"):
            return AxisSpec(key, "step", -2e6, 0.0, 5e5, 5)
        return AxisSpec("s", "step", 8e3, 12e3, 1e3, 5)

    def load_project(self) -> None:
        self._loading = True
        spec = self.state.project.study
        for r in list(self.rows):
            self._drop_row(r)
        allowed = self.allowed()
        axes = [a for a in spec.axes if a.key in allowed] or ([self.default_axis(allowed[0])] if allowed else [])
        for a in axes:
            self._add_row(a)
        self.workers.setValue(spec.workers or 0)
        self._loading = False
        self.result = None
        self.status.setText("Серия ещё не рассчитывалась.")
        self.progress.reset()
        self.refresh()
        self.fill_outputs()
        self.fill_table()

    def refresh(self) -> None:
        p = self.state.project
        c = p.conditions
        kind = ("Камера и сопло" if c.calc == "rocket" else
                WAVE_PROBLEMS.get(c.calc) or EQUILIBRIUM_PROBLEMS.get(c.calc, c.calc))
        comps = ", ".join(x.name for x in p.components) or "компоненты не заданы"
        allowed = self.allowed()
        self.base.setText(f"{kind}; {comps}; ядро NASA CEA {core_version()}. "
                          + ("Можно варьировать: " + ", ".join(q(k).symbol for k in allowed) + "."
                             if allowed else
                             "Для этой постановки серии задаются прямо в исходных условиях (несколько значений "
                             "W₁, M₁, P₁ или T₁ через «;»)."))
        for r in self.rows:
            r.fill_keys(allowed, r.key.currentData() or r._spec_key)
        self.add_axis_btn.setEnabled(bool(allowed) and len(self.rows) < min(MAX_AXES, len(allowed)))
        self.run_btn.setEnabled(bool(allowed) and not self._running())
        self._count_points()

    def _running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    # -------------------------------------------------------------- оси
    def _add_row(self, spec: AxisSpec) -> AxisRow:
        row = AxisRow(self, spec)
        row.fill_keys(self.allowed(), spec.key)
        self.rows.append(row)
        self.axes_box.addWidget(row)
        return row

    def _drop_row(self, row: AxisRow) -> None:
        self.rows.remove(row)
        self.axes_box.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def add_axis(self) -> None:
        used = {r.key.currentData() for r in self.rows}
        free = [k for k in self.allowed() if k not in used and not
                ({"Km", "alpha"} & used and k in ("Km", "alpha")) and not ({"tk", "i"} & used and k in ("tk", "i"))]
        if not free:
            self.state.message.emit("Все допустимые величины уже варьируются.")
            return
        self._add_row(self.default_axis(free[0]))
        self.axes_changed()

    def remove_axis(self, row: AxisRow) -> None:
        if len(self.rows) <= 1:
            self.state.message.emit("Должна остаться хотя бы одна варьируемая величина.")
            return
        self._drop_row(row)
        self.axes_changed()

    def specs(self) -> list[AxisSpec]:
        return [r.spec() for r in self.rows]

    def axes_changed(self) -> None:
        if self._loading:
            return
        try:
            self.state.project.study.axes = self.specs()
        except InputError as exc:
            self.axis_error.setText(str(exc))
            self.points_label.setText("")
            return
        self.state.touch()
        self.refresh()

    def _count_points(self) -> None:
        p = self.state.project
        if not self.allowed():
            self.axis_error.setText("")
            self.points_label.setText("")
            return
        try:
            pts = st.points(p.study, p.conditions, self._is_mixture())
        except InputError as exc:
            self.axis_error.setText(str(exc))
            self.points_label.setText("")
            return
        self.axis_error.setText("")
        n = len(pts)
        auto = n >= st.AUTO_PARALLEL_FROM
        self.points_label.setText(f"Расчётных точек: {n}" + (" — будут считаться в нескольких процессах"
                                                            if auto and not p.study.workers else ""))

    def _workers_changed(self, value: int) -> None:
        if self._loading:
            return
        self.state.project.study.workers = value or None
        self.state.touch()

    # ------------------------------------------------------------ расчёт
    def run(self) -> None:
        if self._running():
            return
        try:
            self.state.project.study.axes = self.specs()
            n = len(st.points(self.state.project.study, self.state.project.conditions, self._is_mixture()))
        except InputError as exc:
            self._set_status(f"Серия не запущена: {exc}", "Bad")
            return
        self.progress.setRange(0, n)
        self.progress.setValue(0)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_status(f"Выполняется серия из {n} расчётов ядром NASA CEA…", "")
        self.thread = StudyThread(self.state.project, self)
        self.thread.progress.connect(lambda d, t: self.progress.setValue(d))
        self.thread.succeeded.connect(self._done)
        self.thread.failed.connect(lambda m: self._set_status(f"Серия не выполнена: {m}", "Bad"))
        self.thread.finished.connect(self._finished)
        self.thread.start()

    def stop(self) -> None:
        if self._running():
            self.thread.cancel()
            self.stop_btn.setEnabled(False)
            self._set_status("Останавливаю серию: текущие точки досчитываются…", "")

    def _finished(self) -> None:
        self.stop_btn.setEnabled(False)
        self.run_btn.setEnabled(bool(self.allowed()))

    def _set_status(self, text: str, obj: str) -> None:
        self.status.setText(text)
        self.status.setObjectName(obj)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _done(self, result: st.StudyResult) -> None:
        self.result = result
        self.state.last_study = result
        self._set_status(result.summary(), "Good" if result.n_failed == 0 else "Warn")
        self.fill_outputs()
        self.fill_table()
        proj = self.state.project
        if proj.id is not None:
            self.state.store.log_calculation(proj.id, "study", proj.to_dict(), self.journal_record(),
                                             core_version())
        self.state.study_ready.emit(result)

    # ---------------------------------------------------------- таблица
    def fill_outputs(self) -> None:
        calc = self.state.project.conditions.calc
        keys, default = (ROCKET_OUT, ROCKET_DEFAULT) if calc == "rocket" else (EQ_OUT, EQ_DEFAULT)
        chosen = {self.outputs.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.outputs.count())
                  if self.outputs.item(i).checkState() == Qt.CheckState.Checked} or set(default)
        self.outputs.blockSignals(True)
        self.outputs.clear()
        for k in keys:
            it = QListWidgetItem(q(k).label())
            it.setData(Qt.ItemDataRole.UserRole, k)
            it.setToolTip(q(k).name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if k in chosen else Qt.CheckState.Unchecked)
            self.outputs.addItem(it)
        self.outputs.blockSignals(False)
        self.section.blockSignals(True)
        self.section.clear()
        sections = self.result.sections if self.result else []
        for i, name in enumerate(sections):
            self.section.addItem(name, i)
        want = self.state.project.study.section
        idx = (want if want >= 0 else len(sections) + want) if sections else -1
        self.section.setCurrentIndex(idx if 0 <= idx < len(sections) else len(sections) - 1)
        self.section.setEnabled(len(sections) > 1)
        self.section.blockSignals(False)

    def _section_changed(self) -> None:
        idx = self.section.currentData()
        if idx is not None and not self._loading:
            n = self.section.count()
            self.state.project.study.section = idx - n if idx == n - 1 else idx
            self.fill_table()

    def selected_outputs(self) -> list[str]:
        return [self.outputs.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.outputs.count())
                if self.outputs.item(i).checkState() == Qt.CheckState.Checked]

    def fill_table(self) -> None:
        t = self.table
        t.clear()
        r = self.result
        if r is None:
            t.setColumnCount(1)
            t.setHorizontalHeaderLabels(["№"])
            t.setRowCount(0)
            return
        outs = [k for k in self.selected_outputs() if k not in r.axes]
        section = self.section.currentData()
        section = -1 if section is None else section
        headers = ["№"] + [q(k).label() for k in r.axes] + [q(k).label() for k in outs] + ["Сходимость"]
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setRowCount(len(r))
        bad = QBrush(QColor("#e5534b"))
        for n in range(len(r)):
            ok = r.converged(n)
            t.setItem(n, 0, ro_item(str(n + 1), True))
            col = 1
            for k in r.axes:
                t.setItem(n, col, ro_item(fmt(q(k).to_display(r.points[n][k])), True))
                col += 1
            for k in outs:
                v = r.value(n, k, section) if ok else math.nan
                t.setItem(n, col, ro_item(fmt(q(k).to_display(v)) if not math.isnan(v) else "—", True))
                col += 1
            status = ro_item("да" if ok else "нет")
            if not ok:
                status.setToolTip(r.message(n))
                status.setText("нет — " + r.message(n))
                for c in range(col + 1):
                    item = t.item(n, c) if c < col else status
                    item.setForeground(bad)
            t.setItem(n, col, status)

    def journal_record(self):
        """Запись серии для журнала: значения осей, сходимость и выведенные величины по точкам."""
        r = self.result
        section = self.section.currentData()
        section = -1 if section is None else section
        outs = self.selected_outputs()
        return StudyRecord(r, section, outs)


class StudyRecord:
    """Сводка серии для журнала проекта (сохраняется в JSON)."""

    def __init__(self, result: st.StudyResult, section: int, outputs: list[str]):
        self.result = result
        self.converged = result.n_failed == 0
        self.message = result.summary()
        self.section = section
        self.outputs = outputs

    def to_dict(self) -> dict:
        r = self.result
        return {
            "type": "study", "calc": r.calc, "axes": r.axes, "cancelled": r.cancelled,
            "section": r.sections[self.section] if r.sections else None,
            "points": [{"params": r.points[n], "converged": r.converged(n),
                        "message": None if r.converged(n) else r.message(n),
                        "values": {k: r.value(n, k, self.section) for k in self.outputs} if r.converged(n) else {}}
                       for n in range(len(r))],
        }
