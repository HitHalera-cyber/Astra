"""Раздел «Исходные условия»."""

from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QRadioButton, QVBoxLayout)

from astra.core import CHEMICAL_MODELS, CeaSession, InputError, WAVE_PROBLEMS
from astra.core.notation import EQUILIBRIUM_PROBLEMS

from ..widgets import ListField, Page, QuantityField, SpeciesListField, fmt, parse_number

CALC_TYPES = ([("rocket", "Камера сгорания и сопло")]
              + [(k, f"{k}: {v}") for k, v in EQUILIBRIUM_PROBLEMS.items()]
              + list(WAVE_PROBLEMS.items()))

# какая величина состояния задаётся в постановке (кроме T)
STATE_KEY = {"H": "i", "U": "u", "S": "s"}
STATE_NAME = {"i": "энтальпию i", "u": "внутреннюю энергию u", "s": "энтропию S"}

WAVE_MODELS = [("equilibrium", "равновесный"), ("frozen", "замороженный")]


class ConditionsPage(Page):
    title = "Исходные условия"
    hint = ("Условия расчёта текущего проекта. Значения проверяются при вводе; подсказка у каждого поля "
            "содержит название, физический смысл, единицу и допустимые значения величины.")

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._loading = False

        # --- постановка
        box = QGroupBox("Постановка задачи")
        f = QFormLayout(box)
        self.calc = QComboBox()
        for key, text in CALC_TYPES:
            self.calc.addItem(text, key)
        self.calc.currentIndexChanged.connect(self._apply)
        f.addRow("Тип расчёта:", self.calc)
        self.body.addWidget(box)

        # --- соотношение компонентов
        self.ratio_box = QGroupBox("Соотношение компонентов")
        g = QGridLayout(self.ratio_box)
        self.by_km = QRadioButton("задать")
        self.by_alpha = QRadioButton("задать")
        grp = QButtonGroup(self)
        grp.addButton(self.by_km)
        grp.addButton(self.by_alpha)
        self.km = QuantityField("Km")
        self.alpha = QuantityField("alpha")
        self.ratio_info = QLabel("")
        self.ratio_info.setObjectName("Muted")
        self.ratio_info.setWordWrap(True)
        g.addWidget(self.by_km, 0, 0)
        g.addWidget(self.km, 0, 1)
        g.addWidget(self.by_alpha, 1, 0)
        g.addWidget(self.alpha, 1, 1)
        g.addWidget(self.ratio_info, 2, 0, 1, 2)
        self.by_km.toggled.connect(self._ratio_mode)
        self.km.edited.connect(lambda: self._ratio_edited("Km"))
        self.alpha.edited.connect(lambda: self._ratio_edited("alpha"))
        self.body.addWidget(self.ratio_box)

        # --- термодинамическое состояние
        self.state_box = QGroupBox("Камера сгорания / заданное состояние")
        v = QVBoxLayout(self.state_box)
        self.pk = QuantityField("pk")
        self.t = QuantityField("t")
        self.vol = QuantityField("v")
        self.by_tk = QCheckBox("Задать температуру камеры Tк вместо энтальпии исходных компонентов")
        self.use_given = QCheckBox("")
        self.given = {"i": QuantityField("i"), "u": QuantityField("u"), "s": QuantityField("s")}
        self.given_hint = QLabel("")
        self.given_hint.setObjectName("Muted")
        self.given_hint.setWordWrap(True)
        for w in (self.pk, self.t, self.vol, *self.given.values()):
            w.edited.connect(self._apply)
        for w in (self.by_tk, self.use_given):
            w.toggled.connect(self._apply)
        for w in (self.pk, self.t, self.vol, self.by_tk, self.use_given, *self.given.values(), self.given_hint):
            v.addWidget(w)
        self.body.addWidget(self.state_box)

        # --- сопло
        self.nozzle_box = QGroupBox("Сопло")
        v = QVBoxLayout(self.nozzle_box)
        self.eps = ListField("eps")
        self.eps_sub = ListField("eps_sub")
        self.pk_p = ListField("pk_p")
        row = QHBoxLayout()
        row.addWidget(QLabel("Модель течения:"))
        self.model = QComboBox()
        for key, text in CHEMICAL_MODELS.items():
            self.model.addItem(text, key)
        self.freeze = QComboBox()
        self.freeze.addItem("состав камеры", "chamber")
        self.freeze.addItem("состав в критическом сечении", "throat")
        row.addWidget(self.model)
        row.addWidget(QLabel("замораживание:"))
        row.addWidget(self.freeze)
        row.addStretch(1)
        self.use_pn = QCheckBox("Учитывать давление окружающей среды Pн (Iуд(Pн), режим истечения)")
        self.pn = QuantityField("pn")
        self.use_mdot = QCheckBox("Задать массовый расход ṁ (площади сечений и тяга)")
        self.mdot = QuantityField("mdot")
        self.use_fac = QCheckBox("Камера конечной площади")
        fac_row = QHBoxLayout()
        self.fac_by_area = QRadioButton("по Fк/Fкр")
        self.fac_by_flux = QRadioButton("по удельному расходу ṁ/Fк")
        fgrp = QButtonGroup(self)
        fgrp.addButton(self.fac_by_area)
        fgrp.addButton(self.fac_by_flux)
        fac_row.addWidget(self.fac_by_area)
        fac_row.addWidget(self.fac_by_flux)
        fac_row.addStretch(1)
        self.eps_k = QuantityField("eps_k")
        self.mass_flux = QuantityField("mass_flux")
        for w in (self.eps, self.eps_sub, self.pk_p, self.pn, self.mdot, self.eps_k, self.mass_flux):
            w.edited.connect(self._apply)
        for w in (self.model, self.freeze):
            w.currentIndexChanged.connect(self._apply)
        for w in (self.use_pn, self.use_mdot, self.use_fac, self.fac_by_area):
            w.toggled.connect(self._apply)
        v.addWidget(self.eps)
        v.addWidget(self.pk_p)
        v.addWidget(self.eps_sub)
        v.addLayout(row)
        for w in (self.use_pn, self.pn, self.use_mdot, self.mdot, self.use_fac):
            v.addWidget(w)
        v.addLayout(fac_row)
        v.addWidget(self.eps_k)
        v.addWidget(self.mass_flux)
        self.body.addWidget(self.nozzle_box)

        # --- ударная волна и детонация
        self.wave_box = QGroupBox("Начальное состояние газа и волна")
        v = QVBoxLayout(self.wave_box)
        self.t1 = ListField("t1")
        self.p1 = ListField("p1")
        self.wave_hint = QLabel("")
        self.wave_hint.setObjectName("Muted")
        self.wave_hint.setWordWrap(True)
        srow = QHBoxLayout()
        self.by_u1 = QRadioButton("задать скорость волны W₁")
        self.by_mach1 = QRadioButton("задать число Маха M₁")
        sgrp = QButtonGroup(self)
        sgrp.addButton(self.by_u1)
        sgrp.addButton(self.by_mach1)
        srow.addWidget(self.by_u1)
        srow.addWidget(self.by_mach1)
        srow.addStretch(1)
        self.u1 = ListField("u1")
        self.mach1 = ListField("mach1")
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("Состав за падающей волной:"))
        self.incident = QComboBox()
        for key, text in WAVE_MODELS:
            self.incident.addItem(text, key)
        mrow.addWidget(self.incident)
        mrow.addWidget(QLabel("отражённая волна:"))
        self.reflected = QComboBox()
        self.reflected.addItem("не рассчитывать", None)
        for key, text in WAVE_MODELS:
            self.reflected.addItem(text + " состав", key)
        mrow.addWidget(self.reflected)
        mrow.addStretch(1)
        self.shock_widgets = [self.by_u1, self.by_mach1, self.u1, self.mach1]
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Состав продуктов детонации:"))
        self.det_model = QComboBox()
        self.det_model.addItem("равновесный", False)
        self.det_model.addItem("замороженный", True)
        drow.addWidget(self.det_model)
        drow.addStretch(1)
        for w in (self.t1, self.p1, self.u1, self.mach1):
            w.edited.connect(self._apply)
        self.by_u1.toggled.connect(self._apply)
        for w in (self.incident, self.reflected, self.det_model):
            w.currentIndexChanged.connect(self._apply)
        v.addWidget(self.t1)
        v.addWidget(self.p1)
        v.addWidget(self.wave_hint)
        v.addLayout(srow)
        v.addWidget(self.u1)
        v.addWidget(self.mach1)
        self.shock_row = mrow
        v.addLayout(mrow)
        self.det_row = drow
        v.addLayout(drow)
        self.body.addWidget(self.wave_box)

        # --- продукты
        box = QGroupBox("Продукты сгорания")
        v = QVBoxLayout(box)
        flags = QHBoxLayout()
        self.ions = QCheckBox("Учитывать ионы")
        self.transport = QCheckBox("Рассчитать переносные свойства (η, λ, Pr)")
        flags.addWidget(self.ions)
        flags.addWidget(self.transport)
        flags.addStretch(1)
        v.addLayout(flags)
        self.only = SpeciesListField("Только", "Рассматривать в продуктах только эти вещества (only в NASA CEA). "
                                               "Пусто — все возможные продукты из базы.")
        self.omit = SpeciesListField("Исключить", "Не рассматривать эти вещества в продуктах (omit в NASA CEA).")
        self.insert = SpeciesListField("Включить конденсат",
                                       "Конденсированные вещества, включаемые в начальное приближение "
                                       "(insert в NASA CEA). Помогает сходимости при образовании конденсата.")
        self.trace = QuantityField("trace", allow_empty=True)
        self.trace.label.setText("Порог trace")
        self.trace.edit.setPlaceholderText("пусто — по умолчанию ядра")
        for w in (self.ions, self.transport):
            w.toggled.connect(self._apply)
        for w in (self.only, self.omit, self.insert, self.trace):
            w.edited.connect(self._apply)
            v.addWidget(w)
        self.body.addWidget(box)

        self.error = QLabel("")
        self.error.setObjectName("Bad")
        self.error.setWordWrap(True)
        self.body.addWidget(self.error)
        self.body.addStretch(1)

        state.project_changed.connect(self.refresh)
        state.data_changed.connect(self._update_ratio_info)
        self.refresh()

    # ------------------------------------------------------------------
    def _session(self) -> CeaSession | None:
        p = self.state.project
        try:
            return CeaSession(p.propellant(), p.products())
        except InputError:
            return None

    def refresh(self) -> None:
        self._loading = True
        c = self.state.project.conditions
        self.calc.setCurrentIndex(max(0, self.calc.findData(c.calc)))
        (self.by_km if c.ratio_kind == "Km" else self.by_alpha).setChecked(True)
        self.pk.set_value(c.pk)
        self.t.set_value(c.t)
        self.vol.set_value(c.v)
        key = self._state_key(c.calc)
        given = {"i": c.given_i, "u": c.given_u, "s": c.given_s}
        self.use_given.setChecked(key is not None and given[key] is not None)
        sess = self._session()
        for k, w in self.given.items():
            w.set_value(given[k] if given[k] is not None else self._reactant_value(sess, k))
        self.by_tk.setChecked(c.chamber_by_tk)
        self.eps.set_values(c.eps)
        self.eps_sub.set_values(c.eps_sub)
        self.pk_p.set_values(c.pk_p)
        self.model.setCurrentIndex(self.model.findData(c.model))
        self.freeze.setCurrentIndex(self.freeze.findData(c.freeze_at))
        self.use_pn.setChecked(c.pn is not None)
        self.pn.set_value(c.pn if c.pn is not None else 101325.0)
        self.use_mdot.setChecked(c.mdot is not None)
        self.mdot.set_value(c.mdot if c.mdot is not None else 1.0)
        self.use_fac.setChecked(c.eps_k is not None or c.mass_flux is not None)
        (self.fac_by_flux if c.mass_flux is not None else self.fac_by_area).setChecked(True)
        self.eps_k.set_value(c.eps_k if c.eps_k is not None else 2.0)
        self.mass_flux.set_value(c.mass_flux if c.mass_flux is not None else 1000.0)
        self.t1.set_values(c.t1)
        self.p1.set_values(c.p1)
        (self.by_u1 if c.shock_by == "u1" else self.by_mach1).setChecked(True)
        self.u1.set_values(c.u1)
        self.mach1.set_values(c.mach1)
        self.incident.setCurrentIndex(max(0, self.incident.findData(c.shock_incident)))
        self.reflected.setCurrentIndex(max(0, self.reflected.findData(c.shock_reflected)))
        self.det_model.setCurrentIndex(1 if c.det_frozen else 0)
        self.ions.setChecked(c.ions)
        self.transport.setChecked(c.transport)
        self.only.set_values(c.only)
        self.omit.set_values(c.omit)
        self.insert.set_values(c.insert)
        self.trace.set_value(c.trace)
        self._loading = False
        self._set_ratio_fields()
        self._visibility()
        self.error.setText("")

    def _reactant_value(self, sess: CeaSession | None, key: str) -> float | None:
        """i, u или S исходных компонентов при T₀ — значение, которое ядро получит по умолчанию."""
        if sess is None:
            return None
        try:
            return sess.reactant_property(sess.km(self.state.project.conditions.ratio()), key)
        except (InputError, ValueError):
            return None

    @staticmethod
    def _state_key(calc: str) -> str | None:
        if calc == "rocket":
            return "i"
        if calc in EQUILIBRIUM_PROBLEMS and calc[0] in STATE_KEY:
            return STATE_KEY[calc[0]]
        return None

    def _set_ratio_fields(self) -> None:
        c = self.state.project.conditions
        sess = self._session()
        self._loading = True
        if sess is not None and sess.is_mixture:
            self.km.set_value(None)
            self.alpha.set_value(None)
        elif c.ratio_kind == "Km":
            self.km.set_value(c.ratio_value)
            self.alpha.set_value(sess.alpha(c.ratio_value) if sess else None)
        else:
            self.alpha.set_value(c.ratio_value)
            self.km.set_value(sess.km(c.ratio()) if sess else None)
        self._loading = False
        self._ratio_mode()
        self._update_ratio_info()

    def _update_ratio_info(self) -> None:
        sess = self._session()
        mixture = all(x.role == "mixture" for x in self.state.project.components) and self.state.project.components
        self.ratio_box.setEnabled(not mixture)
        if mixture:
            self.ratio_info.setText("Состав задан смесью целиком (раздел «Топливо и окислитель»): "
                                    "Kм и α не используются.")
        elif sess is None:
            self.ratio_info.setText("Пересчёт Kм ↔ α станет доступен после задания горючего и окислителя.")
        else:
            self.ratio_info.setText(f"Kм⁰ = {fmt(sess.km0)}; α = Kм / Kм⁰. Второе значение пересчитывается автоматически.")

    def _ratio_mode(self) -> None:
        km_mode = self.by_km.isChecked()
        self.km.edit.setReadOnly(not km_mode)
        self.alpha.edit.setReadOnly(km_mode)
        if not self._loading:
            c = self.state.project.conditions
            new_kind = "Km" if km_mode else "alpha"
            if new_kind != c.ratio_kind:
                field = self.km if km_mode else self.alpha
                try:
                    val = field.value()
                except InputError:
                    val = None
                if val:
                    c.ratio_kind, c.ratio_value = new_kind, val
                    self.state.touch()

    def _ratio_edited(self, kind: str) -> None:
        if self._loading:
            return
        field = self.km if kind == "Km" else self.alpha
        try:
            val = field.value()
            if not val or val <= 0:
                raise InputError("Соотношение компонентов должно быть положительным.")
        except InputError as exc:
            self.error.setText(str(exc))
            return
        c = self.state.project.conditions
        c.ratio_kind, c.ratio_value = kind, val
        self.state.touch()
        self._set_ratio_fields()
        self.error.setText("")

    def _visibility(self) -> None:
        calc = self.calc.currentData()
        rocket = calc == "rocket"
        wave = calc in WAVE_PROBLEMS
        eq = calc in EQUILIBRIUM_PROBLEMS
        self.state_box.setVisible(not wave)
        self.nozzle_box.setVisible(rocket)
        self.wave_box.setVisible(wave)
        self.by_tk.setVisible(rocket)
        self.pk.setVisible(rocket or (eq and calc[1] == "P"))
        self.pk.label.setText(("Pк" if rocket else "P") + ", МПа")
        self.t.setVisible((eq and calc[0] == "T") or (rocket and self.by_tk.isChecked()))
        self.t.label.setText(("Tк" if rocket else "T") + ", К")
        self.vol.setVisible(eq and calc[1] == "V")
        key = self._state_key(calc) if not (rocket and self.by_tk.isChecked()) else None
        self.use_given.setVisible(key is not None)
        if key == "s":
            # энтропия в SP и SV задаётся всегда
            self.use_given.setChecked(True)
            self.use_given.setEnabled(False)
            self.use_given.setText("Энтропия S задаётся явно (обязательно для SP и SV)")
        elif key is not None:
            self.use_given.setEnabled(True)
            self.use_given.setText(f"Задать {STATE_NAME[key]} явно")
            self.given_hint.setText("" if self.use_given.isChecked() else
                                    "Сейчас используется значение исходных компонентов при их начальных "
                                    "температурах T₀ (показано в поле).")
        for k, w in self.given.items():
            w.setVisible(k == key)
            w.edit.setReadOnly(not self.use_given.isChecked())
        self.given_hint.setVisible(key is not None and not self.use_given.isChecked())
        self.freeze.setEnabled(self.model.currentData() == "frozen")
        self.pn.setVisible(self.use_pn.isChecked())
        self.mdot.setVisible(self.use_mdot.isChecked())
        fac = self.use_fac.isChecked()
        self.fac_by_area.setVisible(fac)
        self.fac_by_flux.setVisible(fac)
        self.eps_k.setVisible(fac and self.fac_by_area.isChecked())
        self.mass_flux.setVisible(fac and self.fac_by_flux.isChecked())
        shock = calc == "shock"
        for w in self.shock_widgets:
            w.setVisible(shock)
        self.u1.setVisible(shock and self.by_u1.isChecked())
        self.mach1.setVisible(shock and self.by_mach1.isChecked())
        for lay, show in ((self.shock_row, shock), (self.det_row, calc == "detonation")):
            for i in range(lay.count()):
                item = lay.itemAt(i).widget()
                if item is not None:
                    item.setVisible(show)
        self.wave_hint.setText(
            "Газ перед волной: одна температура T₁ и одно давление P₁; серия — по W₁ или M₁. "
            "Исходные вещества должны быть газообразными." if shock else
            "Для каждого сочетания P₁ и T₁ (значения через «;») выполняется отдельный расчёт.")

    def _apply(self) -> None:
        if self._loading:
            return
        self._visibility()
        c = self.state.project.conditions
        try:
            c.calc = self.calc.currentData()
            c.pk = self.pk.value()
            c.t = self.t.value()
            c.v = self.vol.value()
            c.chamber_by_tk = self.by_tk.isChecked()
            key = self._state_key(c.calc)
            if key is not None:
                use = self.use_given.isChecked() and not (c.calc == "rocket" and c.chamber_by_tk)
                if not use:
                    # показать значение исходных компонентов, которое будет использовано
                    self._loading = True
                    self.given[key].set_value(self._reactant_value(self._session(), key))
                    self._loading = False
                setattr(c, f"given_{key}", self.given[key].value() if use else None)
            c.eps = self.eps.values()
            c.eps_sub = self.eps_sub.values()
            c.pk_p = self.pk_p.values()
            c.model = self.model.currentData()
            c.freeze_at = self.freeze.currentData()
            c.pn = self.pn.value() if self.use_pn.isChecked() else None
            c.mdot = self.mdot.value() if self.use_mdot.isChecked() else None
            fac = self.use_fac.isChecked()
            c.eps_k = self.eps_k.value() if fac and self.fac_by_area.isChecked() else None
            c.mass_flux = self.mass_flux.value() if fac and self.fac_by_flux.isChecked() else None
            c.t1 = self.t1.values()
            c.p1 = self.p1.values()
            c.shock_by = "u1" if self.by_u1.isChecked() else "mach1"
            c.u1 = self.u1.values()
            c.mach1 = self.mach1.values()
            c.shock_incident = self.incident.currentData()
            c.shock_reflected = self.reflected.currentData()
            c.det_frozen = bool(self.det_model.currentData())
            c.ions = self.ions.isChecked()
            c.transport = self.transport.isChecked()
            c.only = self.only.values()
            c.omit = self.omit.values()
            c.insert = self.insert.values()
            c.trace = self.trace.value()
            if c.only and c.omit:
                raise InputError("Списки «Только» и «Исключить» не задаются одновременно.")
        except InputError as exc:
            self.error.setText(str(exc))
        else:
            self.error.setText("")
        self.state.touch()
