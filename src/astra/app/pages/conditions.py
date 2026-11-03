"""Раздел «Исходные условия»."""

from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from astra.core import CHEMICAL_MODELS, CeaSession, InputError
from astra.core.notation import EQUILIBRIUM_PROBLEMS

from ..widgets import ListField, Page, QuantityField, fmt

CALC_TYPES = [("rocket", "Камера сгорания и сопло")] + [(k, f"{k}: {v}") for k, v in EQUILIBRIUM_PROBLEMS.items()]


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
        box = QGroupBox("Соотношение компонентов")
        g = QGridLayout(box)
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
        self.body.addWidget(box)

        # --- термодинамическое состояние
        box = QGroupBox("Камера сгорания / заданное состояние")
        v = QVBoxLayout(box)
        self.pk = QuantityField("pk")
        self.t = QuantityField("t")
        self.vol = QuantityField("v")
        self.by_tk = QCheckBox("Задать температуру камеры Tк вместо энтальпии исходных компонентов")
        for w in (self.pk, self.t, self.vol):
            w.edited.connect(self._apply)
            v.addWidget(w)
        self.by_tk.toggled.connect(self._apply)
        v.addWidget(self.by_tk)
        self.body.addWidget(box)

        # --- сопло
        self.nozzle_box = QGroupBox("Сопло")
        v = QVBoxLayout(self.nozzle_box)
        self.eps = ListField("eps")
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
        self.use_fac = QCheckBox("Камера конечной площади (задать Fк/Fкр)")
        self.eps_k = QuantityField("eps_k")
        for w in (self.eps, self.pk_p, self.pn, self.mdot, self.eps_k):
            w.edited.connect(self._apply)
        for w in (self.model, self.freeze):
            w.currentIndexChanged.connect(self._apply)
        for w in (self.use_pn, self.use_mdot, self.use_fac):
            w.toggled.connect(self._apply)
        v.addWidget(self.eps)
        v.addWidget(self.pk_p)
        v.addLayout(row)
        v.addWidget(self.use_pn)
        v.addWidget(self.pn)
        v.addWidget(self.use_mdot)
        v.addWidget(self.mdot)
        v.addWidget(self.use_fac)
        v.addWidget(self.eps_k)
        self.body.addWidget(self.nozzle_box)

        box = QGroupBox("Продукты сгорания")
        v = QVBoxLayout(box)
        self.ions = QCheckBox("Учитывать ионы")
        self.ions.toggled.connect(self._apply)
        v.addWidget(self.ions)
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
        self.by_tk.setChecked(c.chamber_by_tk)
        self.eps.set_values(c.eps)
        self.pk_p.set_values(c.pk_p)
        self.model.setCurrentIndex(self.model.findData(c.model))
        self.freeze.setCurrentIndex(self.freeze.findData(c.freeze_at))
        self.use_pn.setChecked(c.pn is not None)
        self.pn.set_value(c.pn if c.pn is not None else 101325.0)
        self.use_mdot.setChecked(c.mdot is not None)
        self.mdot.set_value(c.mdot if c.mdot is not None else 1.0)
        self.use_fac.setChecked(c.eps_k is not None)
        self.eps_k.set_value(c.eps_k if c.eps_k is not None else 2.0)
        self.ions.setChecked(c.ions)
        self._loading = False
        self._set_ratio_fields()
        self._visibility()

    def _set_ratio_fields(self) -> None:
        c = self.state.project.conditions
        sess = self._session()
        self._loading = True
        if c.ratio_kind == "Km":
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
        if sess is None:
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
        self.nozzle_box.setVisible(rocket)
        self.by_tk.setVisible(rocket)
        self.pk.setVisible(rocket or calc[1] == "P")
        self.pk.label.setText(("Pк" if rocket else "P") + ", МПа")
        self.t.setVisible((not rocket and calc[0] == "T") or (rocket and self.by_tk.isChecked()))
        self.t.label.setText(("Tк" if rocket else "T") + ", К")
        self.vol.setVisible(not rocket and calc[1] == "V")
        self.freeze.setEnabled(self.model.currentData() == "frozen")
        self.pn.setVisible(self.use_pn.isChecked())
        self.mdot.setVisible(self.use_mdot.isChecked())
        self.eps_k.setVisible(self.use_fac.isChecked())

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
            c.eps = self.eps.values()
            c.pk_p = self.pk_p.values()
            c.model = self.model.currentData()
            c.freeze_at = self.freeze.currentData()
            c.pn = self.pn.value() if self.use_pn.isChecked() else None
            c.mdot = self.mdot.value() if self.use_mdot.isChecked() else None
            c.eps_k = self.eps_k.value() if self.use_fac.isChecked() else None
            c.ions = self.ions.isChecked()
        except InputError as exc:
            self.error.setText(str(exc))
        else:
            self.error.setText("")
        self.state.touch()
