"""Раздел «Исследование сопла»."""

from __future__ import annotations

import math

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QWidget)

from astra.core import CHEMICAL_MODELS, NOZZLE_REGIMES, InputError, classify_regime, core_version, q
from astra.projects import NozzleStudySpec
from astra.projects import nozzle as nz

from ..widgets import ListField, Page, card, fmt, make_table, parse_number, ro_item
from ..worker import JobThread

EPS_MODES = {"count": "по числу точек", "step": "с шагом", "list": "списком"}
FREEZE = {"throat": "в критическом сечении", "chamber": "в камере сгорания"}


def set_status(label: QLabel, text: str, obj: str) -> None:
    label.setText(text)
    label.setObjectName(obj)
    label.style().unpolish(label)
    label.style().polish(label)


def base_text(project) -> str:
    c = project.conditions
    comps = ", ".join(x.name for x in project.components) or "компоненты не заданы"
    if c.calc != "rocket":
        return (f"{comps}. Постановка расчёта в разделе «Исходные условия» — не «Камера сгорания и сопло»: "
                "исследование сопла недоступно.")
    ratio = f"{q(c.ratio_kind).symbol} = {fmt(c.ratio_value)}"
    chamber = (f"Tк = {fmt(c.t)} К" if c.chamber_by_tk else
               "i камеры по исходным компонентам" if c.given_i is None else f"i = {fmt(c.given_i * 1e-3)} кДж/кг")
    area = ("камера бесконечной площади" if c.eps_k is None and c.mass_flux is None else
            f"Fк/Fкр = {fmt(c.eps_k)}" if c.eps_k is not None else f"ṁ/Fк = {fmt(c.mass_flux)} кг/(с·м²)")
    return (f"{comps}; {ratio}; Pк = {fmt(c.pk * 1e-6)} МПа; {chamber}; {area}; ядро NASA CEA {core_version()}. "
            "Камера фиксирована — меняется только степень расширения ε.")


class NozzlePage(Page):
    title = "Исследование сопла"
    hint = ("Состояние камеры фиксируется по исходным условиям проекта; для каждой модели течения выполняется "
            "один вызов ядра NASA CEA со всеми степенями расширения ε, так что камера во всех сечениях одна и та же. "
            "Iуд(Pн) = Iуд.п − Pн·ε·C*/Pк — безотрывное течение; отрыв потока при сильном перерасширении не "
            "моделируется. Режим истечения определяется по соотношению Pа и Pн и не зависит от химической модели.")

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.thread: JobThread | None = None
        self.result: nz.NozzleStudyResult | None = None
        self._loading = False

        frame, lay = card("Камера сгорания")
        self.base = QLabel("")
        self.base.setWordWrap(True)
        lay.addWidget(self.base)
        self.body.addWidget(frame)

        frame, lay = card("Степени расширения и внешнее давление")
        g = QGridLayout()
        g.addWidget(QLabel("ε задаётся:"), 0, 0)
        self.eps_mode = QComboBox()
        for k, t in EPS_MODES.items():
            self.eps_mode.addItem(t, k)
        g.addWidget(self.eps_mode, 0, 1)
        row = QHBoxLayout()
        self.eps_start, self.eps_stop, self.eps_step = QLineEdit(), QLineEdit(), QLineEdit()
        self.eps_count = QSpinBox()
        self.eps_count.setRange(2, 2000)
        self.eps_log = QCheckBox("лог. шкала")
        self.range_labels = [QLabel("от"), QLabel("до"), QLabel("шаг"), QLabel("точек")]
        for w, lab in zip((self.eps_start, self.eps_stop, self.eps_step, self.eps_count), self.range_labels):
            row.addWidget(lab)
            row.addWidget(w, 1)
        row.addWidget(self.eps_log)
        self.range_box = QWidget()
        self.range_box.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        g.addWidget(self.range_box, 0, 2)
        self.eps_list = ListField("eps")
        g.addWidget(self.eps_list, 1, 0, 1, 3)
        self.pn = ListField("pn")
        self.pn.edit.setToolTip("Давления окружающей среды через «;». 0 — истечение в вакуум. "
                                "Для каждого Pн > 0 ядро дополнительно рассчитывает расчётное сечение (Pа = Pн).")
        g.addWidget(self.pn, 2, 0, 1, 3)
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
        mrow.addStretch(1)
        g.addLayout(mrow, 3, 1, 1, 2)
        g.setColumnStretch(2, 1)
        lay.addLayout(g)
        self.error = QLabel("")
        self.error.setObjectName("Bad")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        self.body.addWidget(frame)

        frame, lay = card("Расчёт")
        row = QHBoxLayout()
        self.run_btn = QPushButton("Рассчитать сопло")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        row.addWidget(self.run_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = QLabel("Исследование ещё не выполнялось.")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.chamber = QLabel("")
        self.chamber.setWordWrap(True)
        lay.addWidget(self.chamber)
        self.body.addWidget(frame)

        frame, lay = card("Расчётное расширение (Pа = Pн)")
        self.design_table = make_table(["Pн, МПа"])
        self.design_table.setMinimumHeight(120)
        lay.addWidget(self.design_table)
        self.body.addWidget(frame)

        frame, lay = card("Параметры по степени расширения")
        row = QHBoxLayout()
        row.addWidget(QLabel("Iуд и режим истечения при Pн:"))
        self.pn_view = QComboBox()
        self.pn_view.currentIndexChanged.connect(lambda *_: self.fill_table())
        row.addWidget(self.pn_view)
        row.addStretch(1)
        lay.addLayout(row)
        self.table = make_table(["ε"])
        self.table.setMinimumHeight(380)
        lay.addWidget(self.table, 1)
        self.body.addWidget(frame, 1)

        self.eps_mode.currentIndexChanged.connect(self._changed)
        for w in (self.eps_start, self.eps_stop, self.eps_step):
            w.editingFinished.connect(self._changed)
        self.eps_count.valueChanged.connect(self._changed)
        self.eps_log.toggled.connect(self._changed)
        self.eps_list.edited.connect(self._changed)
        self.pn.edited.connect(self._changed)
        for cb in self.models.values():
            cb.toggled.connect(self._changed)
        self.freeze.currentIndexChanged.connect(self._changed)
        state.project_changed.connect(self.load_project)
        state.data_changed.connect(self.refresh)
        self.load_project()

    # ------------------------------------------------------------ данные
    def load_project(self) -> None:
        self._loading = True
        s = self.state.project.nozzle_study
        self.eps_mode.setCurrentIndex(max(0, self.eps_mode.findData(s.eps_mode)))
        self.eps_start.setText(fmt(s.eps_start, 8))
        self.eps_stop.setText(fmt(s.eps_stop, 8))
        self.eps_step.setText(fmt(s.eps_step, 8))
        self.eps_count.setValue(int(s.eps_count))
        self.eps_log.setChecked(s.eps_log)
        self.eps_list.set_values(s.eps_list)
        self.pn.set_values(s.pn)
        for m, cb in self.models.items():
            cb.setChecked(m in s.models)
        self.freeze.setCurrentIndex(max(0, self.freeze.findData(s.freeze_at)))
        self._loading = False
        self.result = None
        set_status(self.status, "Исследование ещё не выполнялось.", "")
        self.chamber.setText("")
        self._visibility()
        self.refresh()
        self.fill_table()

    def spec(self) -> NozzleStudySpec:
        def num(edit: QLineEdit, what: str) -> float:
            try:
                return parse_number(edit.text())
            except InputError as exc:
                raise InputError(f"ε, {what}: {exc}") from None
        mode = self.eps_mode.currentData()
        s = NozzleStudySpec(eps_mode=mode, models=[m for m, cb in self.models.items() if cb.isChecked()],
                            freeze_at=self.freeze.currentData(), eps_count=self.eps_count.value(),
                            eps_log=self.eps_log.isChecked())
        if mode == "list":
            s.eps_list = self.eps_list.values()
            old = self.state.project.nozzle_study
            s.eps_start, s.eps_stop, s.eps_step = old.eps_start, old.eps_stop, old.eps_step
        else:
            s.eps_start, s.eps_stop = num(self.eps_start, "от"), num(self.eps_stop, "до")
            s.eps_step = num(self.eps_step, "шаг") if mode == "step" else self.state.project.nozzle_study.eps_step
            s.eps_list = list(self.state.project.nozzle_study.eps_list)
        s.pn = self.pn.values()
        return s

    def _visibility(self) -> None:
        mode = self.eps_mode.currentData()
        self.range_box.setVisible(mode != "list")
        self.eps_list.setVisible(mode == "list")
        for w in (self.eps_step, self.range_labels[2]):
            w.setVisible(mode == "step")
        for w in (self.eps_count, self.range_labels[3], self.eps_log):
            w.setVisible(mode == "count")
        self.freeze.setEnabled(self.models["frozen"].isChecked())

    def _changed(self, *_) -> None:
        self._visibility()
        if self._loading:
            return
        try:
            s = self.spec()
            n = len(nz.eps_values(s))
        except InputError as exc:
            self.error.setText(str(exc))
            return
        self.error.setText("")
        self.state.project.nozzle_study = s
        self.state.touch()
        if self.result is None:
            self.status.setText(f"Сечений: {n} × моделей течения: {len(s.models)}.")

    def refresh(self) -> None:
        self.base.setText(base_text(self.state.project))
        self.run_btn.setEnabled(self.state.project.conditions.calc == "rocket")

    # ------------------------------------------------------------ расчёт
    def run(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            return
        try:
            self.state.project.nozzle_study = self.spec()
        except InputError as exc:
            set_status(self.status, f"Расчёт не запущен: {exc}", "Bad")
            return
        self.run_btn.setEnabled(False)
        set_status(self.status, "Выполняется расчёт ядром NASA CEA…", "")
        self.thread = JobThread(self.state.project, lambda p, *_: nz.run_nozzle_study(p), self)
        self.thread.succeeded.connect(self._done)
        self.thread.failed.connect(lambda m: set_status(self.status, f"Расчёт не выполнен: {m}", "Bad"))
        self.thread.finished.connect(self.refresh)
        self.thread.start()

    def _done(self, result: nz.NozzleStudyResult) -> None:
        self.result = result
        n = len(result.eps)
        if result.converged:
            set_status(self.status, f"Расчёт выполнен: {n} сечений, моделей течения — {len(result.by_model)}.", "Good")
        else:
            set_status(self.status, f"Ядро не сошлось — {result.message}", "Bad")
        ch = result.chamber
        self.chamber.setText(
            f"Камера (общая для всех моделей): Tк = {fmt(ch['t'])} К, Pк = {fmt(ch['p'] * 1e-6)} МПа, "
            f"k = {fmt(ch['k'])}, μ = {fmt(ch['mu'])} кг/кмоль, i = {fmt(ch['i'] * 1e-3)} кДж/кг.")
        self.pn_view.blockSignals(True)
        self.pn_view.clear()
        for pn in result.pn:
            self.pn_view.addItem("0 (вакуум)" if pn == 0 else f"{fmt(pn * 1e-6)} МПа", pn)
        self.pn_view.setCurrentIndex(self.pn_view.count() - 1)
        self.pn_view.blockSignals(False)
        self.fill_table()
        proj = self.state.project
        if proj.id is not None:
            self.state.store.log_calculation(proj.id, "nozzle_study", proj.to_dict(), NozzleRecord(result),
                                             core_version())
        self.state.last_nozzle = result
        self.state.nozzle_ready.emit(result)

    # ----------------------------------------------------------- таблицы
    def fill_table(self) -> None:
        t, d = self.table, self.design_table
        r = self.result
        if r is None:
            for tab, h in ((t, "ε"), (d, "Pн, МПа")):
                tab.clear()
                tab.setColumnCount(1)
                tab.setHorizontalHeaderLabels([h])
                tab.setRowCount(0)
            return
        models = list(r.by_model)
        short = {"equilibrium": "равн.", "frozen": "замор."}
        pn = self.pn_view.currentData()
        pn = r.pn[-1] if pn is None else pn
        per = ["p", "t", "M", "w", "isp_vac", "isp_amb"]
        headers = ["ε"]
        for m in models:
            headers += [f"{q(k).label()} ({short[m]})" for k in per]
        if len(models) == 2:
            headers.append("ΔIуд(Pн) равн.−замор., м/с")
        headers.append("Режим истечения")
        t.clear()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setRowCount(len(r.eps))
        bad = QBrush(QColor("#e5534b"))
        exits = {m: r.exits(m) for m in models}
        isp = {m: r.isp(m, pn) for m in models}
        for n, e in enumerate(r.eps):
            t.setItem(n, 0, ro_item(fmt(e), True))
            col = 1
            for m in models:
                ok = r.by_model[m].converged and n < len(exits[m])
                for k in per:
                    if not ok:
                        v = math.nan
                    elif k == "isp_amb":
                        v = isp[m][n]
                    else:
                        v = exits[m][n][k]
                    it = ro_item(fmt(q(k).to_display(v)), True)
                    if k == "isp_amb" and ok and v <= 0:
                        it.setForeground(bad)
                        it.setToolTip("Iуд(Pн) ≤ 0: при таком перерасширении безотрывная оценка теряет смысл.")
                    t.setItem(n, col, it)
                    col += 1
            if len(models) == 2:
                ok = all(r.by_model[m].converged and n < len(exits[m]) for m in models)
                t.setItem(n, col, ro_item(fmt(isp[models[0]][n] - isp[models[1]][n]) if ok else "—", True))
                col += 1
            m0 = models[0]
            regime = (NOZZLE_REGIMES[classify_regime(exits[m0][n]["p"], pn)]
                      if r.by_model[m0].converged and n < len(exits[m0]) else "—")
            if len(models) == 2 and r.by_model[models[1]].converged and n < len(exits[models[1]]):
                other = NOZZLE_REGIMES[classify_regime(exits[models[1]][n]["p"], pn)]
                if other != regime:
                    regime = f"равн.: {regime}; замор.: {other}"
            t.setItem(n, col, ro_item(regime))

        rows = [(pn_, m) for pn_ in r.pn if pn_ > 0 for m in models]
        dh = ["Pн, МПа", "Модель", "ε расч", "Pк/Pа", "Tа, К", "Wа, м/с", "Iуд = Iуд(Pн), м/с", "Iуд.п, м/с"]
        d.clear()
        d.setColumnCount(len(dh))
        d.setHorizontalHeaderLabels(dh)
        d.setRowCount(len(rows))
        for n, (pn_, m) in enumerate(rows):
            pt = r.design.get(m, {}).get(pn_)
            d.setItem(n, 0, ro_item(fmt(pn_ * 1e-6), True))
            d.setItem(n, 1, ro_item(CHEMICAL_MODELS[m]))
            if pt is None:
                why = ("Pн ≥ Pк — расширение невозможно" if pn_ >= r.pk else
                       r.by_model[m].message if not r.by_model[m].converged else "сечение не получено")
                d.setItem(n, 2, ro_item(why))
                continue
            for c, v in enumerate((pt["eps"], pt["pk_p"], pt["t"], pt["w"], pt["isp"], pt["isp_vac"]), start=2):
                d.setItem(n, c, ro_item(fmt(v), True))


class NozzleRecord:
    """Сводка исследования сопла для журнала проекта."""

    def __init__(self, result: nz.NozzleStudyResult):
        self.result = result
        self.converged = result.converged
        self.message = result.message

    def to_dict(self) -> dict:
        r = self.result
        out = {"type": "nozzle_study", "eps": r.eps, "pn": r.pn, "pk": r.pk, "models": {}}
        for m, res in r.by_model.items():
            ex = r.exits(m)
            out["models"][m] = {
                "converged": res.converged, "message": res.message,
                "sections": [{k: p[k] for k in ("eps", "p", "t", "M", "w", "isp", "isp_vac", "c_star")} for p in ex],
                "isp_amb": {str(pn): r.isp(m, pn) for pn in r.pn} if res.converged else {},
                "design": {str(pn): {k: p[k] for k in ("eps", "t", "w", "isp", "isp_vac")}
                           for pn, p in r.design.get(m, {}).items()},
            }
        return out
