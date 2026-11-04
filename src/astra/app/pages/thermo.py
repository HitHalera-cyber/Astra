"""Раздел «Термодинамический расчёт»: запуск ядра и таблицы результатов."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from astra.core import EquilibriumResult, NozzleResult, StatePoint, WAVE_PROBLEMS, WaveResult, core_version, q
from astra.core.notation import EQUILIBRIUM_PROBLEMS

from ..space import EngineDiagram
from ..widgets import Page, card, fmt, make_table, ro_item
from ..worker import CalcThread

TRANSPORT_ROWS = ["eta", "lam", "lam_fr", "pr", "pr_fr"]
NOZZLE_ROWS = ["p", "t", "rho", "i", "H", "s", "cp", "cp_fr", "k", "mu", "mu_c", "a", "w", "M",
               "eps", "pk_p", "c_star", "kt", "kt_p", "isp", "isp_vac", "isp_amb", "kt_n",
               "f_kr", "f_a", "thrust"] + TRANSPORT_ROWS
EQ_ROWS = ["p", "t", "rho", "v", "i", "u", "s", "g", "cp", "cp_fr", "cv", "cv_fr", "k", "mu", "mu_c", "a",
           "Km", "alpha"] + TRANSPORT_ROWS
SHOCK_ROWS = ["w", "M", "w_lab", "w_refl", "p", "t", "rho", "v", "i", "u", "s", "g", "cp", "cp_fr", "cv", "cv_fr",
              "k", "mu", "mu_c", "a", "p_ratio", "t_ratio", "rho_ratio", "mu_ratio"] + TRANSPORT_ROWS
DET_ROWS = ["D", "M_D", "p", "t", "rho", "v", "i", "u", "s", "g", "cp", "cp_fr", "cv", "cv_fr", "k", "mu", "mu_c",
            "a", "p_ratio", "t_ratio", "rho_ratio", "mu_ratio"] + TRANSPORT_ROWS

# карточки основных величин для каждого вида расчёта: (ключ, точка-источник)
METRICS = {
    "nozzle": ["tk", "c_star", "k", "mu", "isp_vac"],
    "equilibrium": ["t", "p", "k", "mu", "a"],
    "shock": ["t", "p", "w_lab", "p_ratio", "rho_ratio"],
    "detonation": ["D", "p", "t", "p_ratio", "k"],
}


def point_header(p: StatePoint) -> str:
    if p.kind in ("supersonic", "subsonic"):
        return f"{p.kind_name}\nε = {fmt(p.target if p.target is not None else p['eps'], 6)}"
    if p.kind == "pressure_ratio":
        return f"{p.kind_name}\nPк/P = {fmt(p.target if p.target is not None else p['pk_p'], 6)}"
    if p.kind.startswith("shock_") and p.target is not None:
        by_mach = p.target_key == "mach1"
        return f"{p.kind_name}\n{'M₁' if by_mach else 'W₁'} = {fmt(p.target)}{'' if by_mach else ' м/с'}"
    if p.kind.startswith("det_") and p.target is not None:
        return f"{p.kind_name}\nP₁ = {fmt(p.target * 1e-6, 5)} МПа, T₁ = {fmt(p.t_target, 5)} К"
    return p.kind_name


def _wave_case_label(r: WaveResult, case: dict) -> str:
    if r.problem == "shock":
        sym = "M₁" if r.inputs.get("mach1") else "W₁"
        unit = "" if sym == "M₁" else " м/с"
        return f"{sym} = {fmt(case['target'])}{unit}"
    p, t = case["target"]
    return f"P₁ = {fmt(p * 1e-6)} МПа, T₁ = {fmt(t)} К"


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

        # схема двигателя: для расчёта камеры и сопла заменяет карточки основных величин
        self.engine = EngineDiagram()
        self.body.addWidget(self.engine)
        self.cards_box = QWidget()
        cards = QHBoxLayout(self.cards_box)
        cards.setContentsMargins(0, 0, 0, 0)
        self.metric_cards: list[tuple[QLabel, QLabel]] = []
        for _ in range(5):
            frame, lay = card()
            name = QLabel("")
            name.setObjectName("Muted")
            name.setWordWrap(True)
            val = QLabel("—")
            val.setObjectName("Metric")
            lay.addWidget(name)
            lay.addWidget(val)
            self.metric_cards.append((name, val))
            cards.addWidget(frame)
        self.body.addWidget(self.cards_box)
        self.metrics: dict[str, QLabel] = {}
        self._set_metric_keys(METRICS["nozzle"])

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
        self._show_engine(None)

    def _set_metric_keys(self, keys: list[str]) -> None:
        self.metrics = {}
        for (name, val), key in zip(self.metric_cards, keys):
            name.setText(q(key).label())
            name.setToolTip(q(key).name)
            val.setText("—")
            self.metrics[key] = val

    def _fill_metrics(self, kind: str, point: StatePoint | None, extra: dict[str, float] | None = None) -> None:
        self._set_metric_keys(METRICS[kind])
        for key, label in self.metrics.items():
            if extra and key in extra:
                v = extra[key]
            else:
                v = point[key] if point is not None else None
            label.setText(fmt(q(key).to_display(v), 5) if v is not None else "—")

    def refresh(self) -> None:
        p = self.state.project
        c = p.conditions
        comps = ", ".join(x.name for x in p.components) or "компоненты не заданы"
        if c.calc == "rocket":
            kind = "Камера и сопло"
        else:
            kind = WAVE_PROBLEMS.get(c.calc) or EQUILIBRIUM_PROBLEMS[c.calc]
        if p.components and all(x.role == "mixture" for x in p.components):
            ratio = "состав задан смесью"
        else:
            ratio = f"Kм = {fmt(c.ratio_value)}" if c.ratio_kind == "Km" else f"α = {fmt(c.ratio_value)}"
        self.summary.setText(f"{kind}; {comps}; {ratio}; ядро NASA CEA {core_version()}")
        rocket = c.calc == "rocket"
        self.engine.setVisible(rocket)
        self.cards_box.setVisible(not rocket)

    def clear(self) -> None:
        self.status.setText("Расчёт ещё не выполнялся.")
        self._set_metric_keys(METRICS["nozzle"])
        self.values_table.setRowCount(0)
        self.comp_table.setRowCount(0)
        self.notes.setText("")
        self._show_engine(None)
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

    # --- схема двигателя
    def apply_theme(self, name: str) -> None:
        self.engine.set_theme(name)

    def _show_engine(self, result: NozzleResult | None) -> None:
        """Значения ядра по сечениям: камера, критическое сечение, последнее сечение сопла."""
        def val(p: StatePoint | None, key: str, scale: float | None = None, digits: int = 4) -> str:
            if p is None or key not in p.values or p[key] is None:
                return "—"
            v = p[key] * scale if scale is not None else q(key).to_display(p[key])
            return fmt(v, digits)

        ch = th = ex = None
        if result is not None:
            ch = next((p for p in result.points if p.kind in ("chamber", "chamber_end")), None)
            th = next((p for p in result.points if p.kind == "throat"), None)
            exits = result.exits()
            ex = exits[-1] if exits else None
        if ex is None:
            exit_title = "СРЕЗ СОПЛА"
        elif ex.kind == "pressure_ratio":
            exit_title = f"СРЕЗ СОПЛА · Pк/P = {val(ex, 'pk_p', 1.0, 4)}"
        else:
            exit_title = f"СРЕЗ СОПЛА · ε = {val(ex, 'eps', 1.0, 4)}"
        stations = [
            {"title": "КАМЕРА СГОРАНИЯ", "rows": [("Pк", val(ch, "p"), q("p").unit), ("Tк", val(ch, "t"), "К"),
                                                  ("k", val(ch, "k"), "")]},
            {"title": "КРИТИЧЕСКОЕ СЕЧЕНИЕ", "rows": [("Tкр", val(th, "t"), "К"), ("Wкр", val(th, "w"), "м/с"),
                                                      ("M", val(th, "M"), "")]},
            {"title": exit_title, "rows": [("Pа", val(ex, "p", 1e-3), "кПа"), ("Tа", val(ex, "t"), "К"),
                                           ("Wа", val(ex, "w"), "м/с")]},
        ]
        src = next((p for p in (result.points if result else []) if "c_star" in p.values), None)
        self.engine.set_data(stations, ("УДЕЛЬНЫЙ ИМПУЛЬС В ПУСТОТЕ", val(ex, "isp_vac", None, 5),
                                        f"{q('isp_vac').label()} · C* = {val(src, 'c_star', None, 5)} м/с"))

    # --- отображение
    def show_result(self, result: EquilibriumResult | NozzleResult | WaveResult) -> None:
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
            nozzle_pts = [p for p in result.points if "c_star" in p.values]
            self._fill_metrics("nozzle", chamber, {
                "tk": chamber["t"] if chamber else None,
                "c_star": nozzle_pts[0]["c_star"] if nozzle_pts else None,
                "isp_vac": exits[-1]["isp_vac"] if exits else None})
            if exits:
                self.metric_cards[4][0].setText(q("isp_vac").label() + f" (ε = {fmt(exits[-1]['eps'], 4)})")
            self._show_engine(result)
        elif isinstance(result, WaveResult):
            rows = SHOCK_ROWS if result.problem == "shock" else DET_ROWS
            points = result.points
            notes = [f"<b>Постановка:</b> {result.problem_name}"] + [f"• {a}" for a in result.assumptions]
            notes += ["", "<b>Варианты:</b>"] + [
                f"• {i + 1}: {_wave_case_label(result, c)} — {'расчёт выполнен' if c['converged'] else c['message']}"
                for i, c in enumerate(result.cases)]
            if result.warnings:
                notes += ["", "<b>Сообщения ядра:</b>"] + [f"• {w}" for w in result.warnings]
            after = [p for p in points if p.kind in ("shock_incident", "det_products")]
            self._fill_metrics(result.problem, after[0] if after else None)
            if len(result.cases) > 1:
                first = _wave_case_label(result, result.cases[0])
                for name, _ in self.metric_cards:
                    name.setText(f"{name.text()} ({first})")
        else:
            points, rows = [result.point], EQ_ROWS
            notes = [f"<b>Постановка:</b> {EQUILIBRIUM_PROBLEMS[result.problem]}"]
            if result.inputs.get("state_from_reactants"):
                key = {"H": "i", "U": "u", "S": "s"}[result.problem[0]]
                qt = q(key)
                notes.append(f"• {qt.symbol} = {fmt(qt.to_display(result.inputs[key]))} {qt.unit} — "
                             "по исходным компонентам при их начальных температурах.")
            self._fill_metrics("equilibrium", result.point)
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
