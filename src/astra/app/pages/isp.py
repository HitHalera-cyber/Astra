"""Раздел «Удельный импульс»."""

from __future__ import annotations

import math

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                               QPushButton, QSpinBox)

from astra.core import CHEMICAL_MODELS, InputError, core_version, q
from astra.projects import IspStudySpec
from astra.projects import nozzle as nz

from ..widgets import ListField, Page, card, fmt, make_table, parse_number, ro_item
from ..worker import JobThread
from .nozzle import FREEZE, base_text, set_status

RATIO_MODES = {"count": "по числу точек", "step": "с шагом"}


class IspPage(Page):
    title = "Удельный импульс"
    hint = ("Iуд в зависимости от Kм или α при нескольких степенях расширения ε, давлениях окружающей среды Pн "
            "и моделях течения. Каждая точка — полный расчёт камеры и сопла ядром NASA CEA при остальных исходных "
            "условиях проекта. Максимум Iуд уточняется расчётами ядра (золотое сечение) около лучшей точки сетки; "
            "если лучшая точка на границе диапазона, это сообщается — внутренний максимум не придумывается.")

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.thread: JobThread | None = None
        self.result: nz.IspStudyResult | None = None
        self._loading = False

        frame, lay = card("Исходные условия")
        self.base = QLabel("")
        self.base.setWordWrap(True)
        lay.addWidget(self.base)
        self.body.addWidget(frame)

        frame, lay = card("Варьирование и варианты")
        g = QGridLayout()
        g.addWidget(QLabel("Варьируется:"), 0, 0)
        row = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItem("α — коэффициент избытка окислителя", "alpha")
        self.kind.addItem("Kм — массовое соотношение компонентов", "Km")
        self.mode = QComboBox()
        for k, t in RATIO_MODES.items():
            self.mode.addItem(t, k)
        self.start_e, self.stop_e, self.step_e = QLineEdit(), QLineEdit(), QLineEdit()
        self.count = QSpinBox()
        self.count.setRange(3, 2000)
        self.step_label, self.count_label = QLabel("шаг"), QLabel("точек")
        row.addWidget(self.kind, 2)
        row.addWidget(self.mode, 1)
        for lab, w in ((QLabel("от"), self.start_e), (QLabel("до"), self.stop_e), (self.step_label, self.step_e),
                       (self.count_label, self.count)):
            row.addWidget(lab)
            row.addWidget(w, 1)
        g.addLayout(row, 0, 1)
        self.eps = ListField("eps")
        g.addWidget(self.eps, 1, 0, 1, 2)
        self.pn = ListField("pn")
        self.pn.edit.setToolTip("Давления окружающей среды через «;». 0 — пустота (Iуд.п).")
        g.addWidget(self.pn, 2, 0, 1, 2)
        g.addWidget(QLabel("Модели течения:"), 3, 0)
        mrow = QHBoxLayout()
        self.models = {m: QCheckBox(CHEMICAL_MODELS[m]) for m in nz.MODELS}
        for cb in self.models.values():
            mrow.addWidget(cb)
        mrow.addWidget(QLabel("замораживание состава:"))
        self.freeze = QComboBox()
        for k, t in FREEZE.items():
            self.freeze.addItem(t, k)
        mrow.addWidget(self.freeze)
        self.find_max = QCheckBox("искать максимум Iуд")
        mrow.addWidget(self.find_max)
        mrow.addStretch(1)
        g.addLayout(mrow, 3, 1)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        self.error = QLabel("")
        self.error.setObjectName("Bad")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        self.body.addWidget(frame)

        frame, lay = card("Расчёт")
        row = QHBoxLayout()
        self.run_btn = QPushButton("Рассчитать Iуд")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        self.progress = QProgressBar()
        self.progress.setFormat("%v из %m")
        row.addWidget(self.run_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(self.progress, 1)
        lay.addLayout(row)
        self.status = QLabel("Расчёт ещё не выполнялся.")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.body.addWidget(frame)

        frame, lay = card("Максимумы удельного импульса")
        self.opt_table = make_table(["Вариант"])
        self.opt_table.setMinimumHeight(160)
        lay.addWidget(self.opt_table)
        self.body.addWidget(frame)

        frame, lay = card("Iуд по соотношению компонентов, м/с")
        self.table = make_table(["Kм"])
        self.table.setMinimumHeight(360)
        lay.addWidget(self.table, 1)
        self.body.addWidget(frame, 1)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.mode.currentIndexChanged.connect(self._changed)
        for w in (self.start_e, self.stop_e, self.step_e):
            w.editingFinished.connect(self._changed)
        self.count.valueChanged.connect(self._changed)
        self.eps.edited.connect(self._changed)
        self.pn.edited.connect(self._changed)
        for cb in self.models.values():
            cb.toggled.connect(self._changed)
        self.freeze.currentIndexChanged.connect(self._changed)
        self.find_max.toggled.connect(self._changed)
        state.project_changed.connect(self.load_project)
        state.data_changed.connect(self.refresh)
        self.load_project()

    # ------------------------------------------------------------ данные
    def load_project(self) -> None:
        self._loading = True
        s = self.state.project.isp_study
        self.kind.setCurrentIndex(max(0, self.kind.findData(s.ratio_kind)))
        self.mode.setCurrentIndex(max(0, self.mode.findData(s.mode)))
        self.start_e.setText(fmt(s.start, 8))
        self.stop_e.setText(fmt(s.stop, 8))
        self.step_e.setText(fmt(s.step, 8))
        self.count.setValue(int(s.count))
        self.eps.set_values(s.eps)
        self.pn.set_values(s.pn)
        for m, cb in self.models.items():
            cb.setChecked(m in s.models)
        self.freeze.setCurrentIndex(max(0, self.freeze.findData(s.freeze_at)))
        self.find_max.setChecked(s.find_max)
        self._loading = False
        self.result = None
        self.progress.reset()
        set_status(self.status, "Расчёт ещё не выполнялся.", "")
        self._visibility()
        self.refresh()
        self.fill_tables()

    def spec(self) -> IspStudySpec:
        sym = q(self.kind.currentData()).symbol

        def num(edit: QLineEdit, what: str) -> float:
            try:
                return parse_number(edit.text())
            except InputError as exc:
                raise InputError(f"{sym}, {what}: {exc}") from None
        mode = self.mode.currentData()
        return IspStudySpec(
            ratio_kind=self.kind.currentData(), mode=mode, start=num(self.start_e, "от"), stop=num(self.stop_e, "до"),
            step=num(self.step_e, "шаг") if mode == "step" else self.state.project.isp_study.step,
            count=self.count.value(), eps=self.eps.values(), pn=self.pn.values(),
            models=[m for m, cb in self.models.items() if cb.isChecked()], freeze_at=self.freeze.currentData(),
            find_max=self.find_max.isChecked())

    def _visibility(self) -> None:
        step = self.mode.currentData() == "step"
        for w in (self.step_e, self.step_label):
            w.setVisible(step)
        for w in (self.count, self.count_label):
            w.setVisible(not step)
        self.freeze.setEnabled(self.models["frozen"].isChecked())

    def _kind_changed(self) -> None:
        if self._loading:
            return
        # диапазон по умолчанию для другой величины — вокруг значения исходных условий
        c = self.state.project.conditions
        if self.kind.currentData() == "Km":
            base = c.ratio_value if c.ratio_kind == "Km" else 3.0
            lo, hi, st = base * 0.6, base * 1.4, base * 0.1
        else:
            lo, hi, st = 0.5, 1.2, 0.05
        self.start_e.setText(fmt(lo, 6))
        self.stop_e.setText(fmt(hi, 6))
        self.step_e.setText(fmt(st, 6))
        self._changed()

    def _changed(self, *_) -> None:
        self._visibility()
        if self._loading:
            return
        try:
            s = self.spec()
            n = len(nz.ratio_values(s))
        except InputError as exc:
            self.error.setText(str(exc))
            return
        self.error.setText("")
        self.state.project.isp_study = s
        self.state.touch()
        if self.result is None:
            self.status.setText(f"Расчётов камеры и сопла: {n * len(s.models)} (по {len(set(s.eps))} ε в каждом).")

    def refresh(self) -> None:
        self.base.setText(base_text(self.state.project).replace(
            "Камера фиксирована — меняется только степень расширения ε.",
            "Варьируется только соотношение компонентов."))
        running = self.thread is not None and self.thread.isRunning()
        self.run_btn.setEnabled(self.state.project.conditions.calc == "rocket" and not running)

    # ------------------------------------------------------------ расчёт
    def run(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            return
        try:
            s = self.spec()
            n = len(nz.ratio_values(s)) * len(s.models)
            self.state.project.isp_study = s
        except InputError as exc:
            set_status(self.status, f"Расчёт не запущен: {exc}", "Bad")
            return
        self.progress.setRange(0, n)
        self.progress.setValue(0)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        set_status(self.status, f"Выполняется {n} расчётов ядром NASA CEA"
                   + (", затем уточнение максимумов…" if s.find_max else "…"), "")
        self.thread = JobThread(self.state.project,
                                lambda p, prog, canc: nz.run_isp_study(p, progress=prog, cancelled=canc, workers=None),
                                self)
        self.thread.progress.connect(lambda d, t: self.progress.setValue(d))
        self.thread.succeeded.connect(self._done)
        self.thread.failed.connect(lambda m: set_status(self.status, f"Расчёт не выполнен: {m}", "Bad"))
        self.thread.finished.connect(self._finished)
        self.thread.start()

    def stop(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.stop_btn.setEnabled(False)
            set_status(self.status, "Останавливаю расчёт: текущие точки досчитываются…", "")

    def _finished(self) -> None:
        self.stop_btn.setEnabled(False)
        self.refresh()

    def _done(self, result: nz.IspStudyResult) -> None:
        self.result = result
        self.state.last_isp = result
        edge = any(o.note.startswith("Наибольшее") for o in result.optima)
        obj = "Good" if result.n_failed == 0 and not result.cancelled and not edge else "Warn"
        text = result.summary()
        if edge:
            text += " Для части вариантов максимум лежит на границе диапазона — расширьте диапазон."
        set_status(self.status, text, obj)
        self.fill_tables()
        proj = self.state.project
        if proj.id is not None:
            self.state.store.log_calculation(proj.id, "isp_study", proj.to_dict(), IspRecord(result),
                                             core_version())
        self.state.isp_ready.emit(result)

    # ----------------------------------------------------------- таблицы
    def fill_tables(self) -> None:
        t, o = self.table, self.opt_table
        r = self.result
        if r is None:
            for tab, h in ((t, "Kм"), (o, "Вариант")):
                tab.clear()
                tab.setColumnCount(1)
                tab.setHorizontalHeaderLabels([h])
                tab.setRowCount(0)
            return
        curves = r.curves()
        tk_cols = r.models[:1]          # камера не зависит от модели течения в сопле
        headers = ["Kм", "α", "Tк, К"]
        headers += [c.label for c in curves] + ["Сходимость"]
        t.clear()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setRowCount(len(r.ratios))
        bad = QBrush(QColor("#e5534b"))
        values = [r.isp(c) for c in curves]
        tks = {m: r.chamber_t(m) for m in r.models}
        best = [max((v for v in vals if not math.isnan(v)), default=math.nan) for vals in values]
        for n, x in enumerate(r.ratios):
            km = x if r.ratio_kind == "Km" else x * r.km0
            t.setItem(n, 0, ro_item(fmt(km), True))
            t.setItem(n, 1, ro_item(fmt(km / r.km0), True))
            col = 2
            for m in tk_cols:
                t.setItem(n, col, ro_item(fmt(tks[m][n]), True))
                col += 1
            for j, vals in enumerate(values):
                it = ro_item(fmt(vals[n]), True)
                if not math.isnan(vals[n]) and vals[n] == best[j]:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setToolTip("Наибольшее значение на сетке")
                t.setItem(n, col, it)
                col += 1
            msgs = [f"{CHEMICAL_MODELS[m]}: {r.failed(m, n)}" for m in r.models if r.failed(m, n)]
            st = ro_item("; ".join(msgs) if msgs else "да")
            if msgs:
                st.setToolTip(st.text())
                for c in range(col):
                    t.item(n, c).setForeground(bad)
                st.setForeground(bad)
            t.setItem(n, col, st)

        oh = ["Вариант", "Kм опт", "α опт", "Iуд max, м/с", "Tк, К", "Расчётов ядра", "Примечание"]
        o.clear()
        o.setColumnCount(len(oh))
        o.setHorizontalHeaderLabels(oh)
        o.setRowCount(len(r.optima))
        for n, opt in enumerate(r.optima):
            o.setItem(n, 0, ro_item(opt.curve.label))
            for c, v in enumerate((opt.km, opt.alpha, opt.isp, opt.tk), start=1):
                o.setItem(n, c, ro_item(fmt(v), True))
            o.setItem(n, 5, ro_item(str(opt.evaluations), True))
            note = ro_item(opt.note)
            note.setToolTip(opt.note)
            if not opt.note.startswith("Внутренний"):
                note.setForeground(QBrush(QColor("#e0a43a")))
            o.setItem(n, 6, note)


class IspRecord:
    """Сводка исследования Iуд для журнала проекта."""

    def __init__(self, result: nz.IspStudyResult):
        self.result = result
        self.converged = result.n_failed == 0
        self.message = result.summary()

    def to_dict(self) -> dict:
        r = self.result
        return {
            "type": "isp_study", "ratio_kind": r.ratio_kind, "ratios": r.ratios, "eps": r.eps, "pn": r.pn,
            "models": r.models, "cancelled": r.cancelled,
            "curves": [{"model": c.model, "eps": c.eps, "pn": c.pn, "isp": r.isp(c)} for c in r.curves()],
            "failed": {m: {str(n): r.failed(m, n) for n in range(len(r.ratios)) if r.failed(m, n)} for m in r.models},
            "optima": [{"model": o.curve.model, "eps": o.curve.eps, "pn": o.curve.pn, "Km": o.km, "alpha": o.alpha,
                        "isp": o.isp, "tk": o.tk, "evaluations": o.evaluations, "note": o.note} for o in r.optima],
        }
