"""Раздел «Термодинамический расчёт»: запуск ядра и таблицы результатов."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from astra.core import EquilibriumResult, NozzleResult, StatePoint, core_version, q
from astra.core.notation import EQUILIBRIUM_PROBLEMS

from ..widgets import Page, card, fmt, make_table, ro_item
from ..worker import CalcThread

NOZZLE_ROWS = ["p", "t", "rho", "i", "H", "s", "cp", "cp_fr", "k", "mu", "mu_c", "a", "w", "M",
               "eps", "pk_p", "c_star", "kt", "kt_p", "isp", "isp_vac", "isp_amb", "kt_n",
               "f_kr", "f_a", "thrust"]
EQ_ROWS = ["p", "t", "rho", "v", "i", "u", "s", "g", "cp", "cp_fr", "cv", "cv_fr", "k", "mu", "mu_c", "a",
           "Km", "alpha"]


def point_header(p: StatePoint) -> str:
    if p.kind in ("supersonic", "subsonic"):
        return f"{p.kind_name}\nε = {fmt(p.target if p.target is not None else p['eps'], 6)}"
    if p.kind == "pressure_ratio":
        return f"{p.kind_name}\nPк/P = {fmt(p.target if p.target is not None else p['pk_p'], 6)}"
    return p.kind_name


class ThermoPage(Page):
    title = "Термодинамический расчёт"
    hint = ("Расчёт выполняется оригинальным ядром NASA CEA по исходным данным проекта. "
            "Каждый расчёт записывается в журнал проекта.")

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.thread: CalcThread | None = None

        row = QHBoxLayout()
        self.run_btn = QPushButton("Рассчитать")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        row.addWidget(self.run_btn)
        row.addWidget(self.summary, 1)
        self.body.addLayout(row)

        self.status = QLabel("Расчёт ещё не выполнялся.")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)

        cards = QHBoxLayout()
        self.metrics: dict[str, QLabel] = {}
        for key in ("tk", "c_star", "k", "mu", "isp_vac"):
            frame, lay = card()
            name = QLabel(q(key).label())
            name.setObjectName("Muted")
            val = QLabel("—")
            val.setObjectName("Metric")
            lay.addWidget(name)
            lay.addWidget(val)
            self.metrics[key] = val
            cards.addWidget(frame)
        self.body.addLayout(cards)

        self.tabs = QTabWidget()
        self.values_table = make_table(["Величина"])
        self.comp_table = make_table(["Вещество"])
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        notes_w = QWidget()
        nl = QVBoxLayout(notes_w)
        nl.addWidget(self.notes)
        nl.addStretch(1)
        self.tabs.addTab(self.values_table, "Параметры")
        self.tabs.addTab(self.comp_table, "Состав продуктов (мольные доли)")
        self.tabs.addTab(notes_w, "Предположения и предупреждения")
        self.tabs.setMinimumHeight(460)
        self.body.addWidget(self.tabs, 1)

        state.project_changed.connect(self.clear)
        state.data_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        c = self.state.project.conditions
        comps = ", ".join(x.name for x in self.state.project.components) or "компоненты не заданы"
        kind = "Камера и сопло" if c.calc == "rocket" else EQUILIBRIUM_PROBLEMS[c.calc]
        ratio = f"Kм = {fmt(c.ratio_value)}" if c.ratio_kind == "Km" else f"α = {fmt(c.ratio_value)}"
        self.summary.setText(f"{kind}; {comps}; {ratio}; ядро NASA CEA {core_version()}")

    def clear(self) -> None:
        self.status.setText("Расчёт ещё не выполнялся.")
        for v in self.metrics.values():
            v.setText("—")
        self.values_table.setRowCount(0)
        self.comp_table.setRowCount(0)
        self.notes.setText("")
        self.refresh()

    # --- запуск
    def run(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            return
        self.run_btn.setEnabled(False)
        self.status.setObjectName("")
        self.status.setText("Выполняется расчёт ядром NASA CEA…")
        self.thread = CalcThread(self.state.project, self)
        self.thread.succeeded.connect(self._done)
        self.thread.failed.connect(self._failed)
        self.thread.finished.connect(lambda: self.run_btn.setEnabled(True))
        self.thread.start()

    def _failed(self, msg: str) -> None:
        self._set_status(f"Расчёт не выполнен: {msg}", "Bad")
        self.state.message.emit("Расчёт не выполнен.")

    def _set_status(self, text: str, obj: str) -> None:
        self.status.setText(text)
        self.status.setObjectName(obj)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _done(self, result) -> None:
        self.show_result(result)
        proj = self.state.project
        if proj.id is not None:
            self.state.store.log_calculation(proj.id, proj.conditions.calc, proj.to_dict(), result, core_version())
        self.state.last_result = result
        self.state.result_ready.emit(result)

    # --- отображение
    def show_result(self, result: EquilibriumResult | NozzleResult) -> None:
        if result.converged:
            self._set_status(result.message, "Good")
        else:
            self._set_status(result.message + " Значения, не полученные от ядра, показаны как «—».", "Bad")

        if isinstance(result, NozzleResult):
            points, rows = result.points, NOZZLE_ROWS
            notes = ["<b>Модель:</b> " + result.model_name] + [f"• {a}" for a in result.assumptions]
            if result.warnings:
                notes += ["", "<b>Предупреждения:</b>"] + [f"• {w}" for w in result.warnings]
            chamber = next((p for p in result.points if p.kind in ("chamber", "chamber_end")), None)
            exits = result.exits()
            last = exits[-1] if exits else None
            self.metrics["tk"].setText(fmt(chamber["t"], 5) if chamber else "—")
            nozzle_pts = [p for p in result.points if "c_star" in p.values]
            self.metrics["c_star"].setText(fmt(nozzle_pts[0]["c_star"], 5) if nozzle_pts else "—")
            self.metrics["k"].setText(fmt(chamber["k"], 5) if chamber else "—")
            self.metrics["mu"].setText(fmt(chamber["mu"], 5) if chamber else "—")
            self.metrics["isp_vac"].setText(fmt(last["isp_vac"], 5) if last else "—")
        else:
            points, rows = [result.point], EQ_ROWS
            notes = [f"<b>Постановка:</b> {EQUILIBRIUM_PROBLEMS[result.problem]}"]
            for k in ("c_star", "isp_vac"):
                self.metrics[k].setText("—")
            self.metrics["tk"].setText(fmt(result["t"], 5))
            self.metrics["k"].setText(fmt(result["k"], 5))
            self.metrics["mu"].setText(fmt(result["mu"], 5))
        self.notes.setText("<br>".join(notes))

        # параметры: строки — величины, столбцы — точки
        t = self.values_table
        t.clear()
        t.setColumnCount(1 + len(points))
        t.setHorizontalHeaderLabels(["Величина"] + [point_header(p) for p in points])
        used = [k for k in rows if any(k in p.values for p in points)]
        extra = 1 if any(p.regime for p in points) else 0
        t.setRowCount(len(used) + extra)
        for r, key in enumerate(used):
            qt = q(key)
            name = ro_item(qt.label())
            name.setToolTip(f"{qt.name}. {qt.meaning}")
            t.setItem(r, 0, name)
            for c, p in enumerate(points, start=1):
                t.setItem(r, c, ro_item(fmt(qt.to_display(p[key])) if key in p.values else "—", True))
        if extra:
            r = len(used)
            t.setItem(r, 0, ro_item("Режим истечения"))
            for c, p in enumerate(points, start=1):
                t.setItem(r, c, ro_item(p.regime_name or "—"))

        # состав
        species: dict[str, float] = {}
        for p in points:
            for sp, x in p.major_species(5e-6).items():
                species[sp] = max(species.get(sp, 0.0), x)
        names = sorted(species, key=lambda s: -species[s])
        ct = self.comp_table
        ct.clear()
        ct.setColumnCount(1 + len(points))
        ct.setHorizontalHeaderLabels(["Вещество"] + [point_header(p) for p in points])
        ct.setRowCount(len(names))
        for r, sp in enumerate(names):
            ct.setItem(r, 0, ro_item(sp))
            for c, p in enumerate(points, start=1):
                x = p.mole_fractions.get(sp)
                ct.setItem(r, c, ro_item(fmt(x, 5) if x is not None else "—", True))
