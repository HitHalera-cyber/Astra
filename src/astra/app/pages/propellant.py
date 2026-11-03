"""Раздел «Топливо и окислитель»."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QTableWidgetItem, QVBoxLayout)

from astra.core import CeaSession, InputError, species_db
from astra.projects import ComponentSpec

from ..widgets import Page, card, fmt, make_table, parse_number, ro_item

ROLES = [("fuel", "Горючее"), ("oxidizer", "Окислитель"), ("mixture", "Компонент смеси")]


class SpeciesDialog(QDialog):
    """Выбор вещества из базы NASA CEA с поиском."""

    def __init__(self, parent=None, query: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Выбор вещества из базы NASA CEA")
        self.resize(760, 480)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(query)
        self.search.setPlaceholderText("Имя, формула или описание: H2(L), RP-1, N2O4, kerosene…")
        lay.addWidget(self.search)
        self.table = make_table(["Вещество", "Формула", "Фаза", "μ, г/моль", "ΔHf°, кДж/моль", "T, К"])
        lay.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Выбрать")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.search.textChanged.connect(self.fill)
        self.table.doubleClicked.connect(lambda *_: self.accept())
        self.fill()

    def fill(self) -> None:
        found = species_db.search(self.search.text(), limit=300)
        self.table.setRowCount(len(found))
        for r, s in enumerate(found):
            temp = fmt(s.t_assigned) if s.t_assigned is not None else f"{fmt(s.t_min)}…{fmt(s.t_max)}"
            for c, text in enumerate([s.name, s.formula_text, s.phase_name, fmt(s.molar_mass),
                                      fmt(s.hf / 1000), temp]):
                self.table.setItem(r, c, ro_item(text, c >= 3))
        if found:
            self.table.selectRow(0)

    def selected(self) -> species_db.Species | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return species_db.by_name(item.text()) if item else None


def default_t0(sp: species_db.Species) -> float:
    if sp.t_assigned is not None:
        return sp.t_assigned
    return 298.15 if sp.t_min <= 298.15 <= sp.t_max else sp.t_min


class PropellantPage(Page):
    title = "Топливо и окислитель"
    hint = ("Компоненты выбираются из базы NASA CEA. Доли задаются внутри горючего и внутри окислителя "
            "(нормируются ядром); соотношение между ними — в разделе «Исходные условия». "
            "Для газовой смеси (например, для ударной волны) все компоненты задаются как «компонент смеси» "
            "с долями в смеси — тогда Kм и α не используются.")

    COLS = ["Вещество", "Роль", "Доля", "T₀, К", "Формула", "Фаза"]

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._loading = False

        frame, lay = card()
        row = QHBoxLayout()
        row.addWidget(QLabel("Доли компонентов:"))
        self.basis = QComboBox()
        self.basis.addItem("массовые", "mass")
        self.basis.addItem("мольные", "mole")
        self.basis.currentIndexChanged.connect(self._basis_changed)
        row.addWidget(self.basis)
        row.addStretch(1)
        self.add_fuel = QPushButton("Добавить горючее…")
        self.add_ox = QPushButton("Добавить окислитель…")
        self.add_mix = QPushButton("Добавить компонент смеси…")
        self.remove = QPushButton("Удалить выбранный")
        self.add_fuel.clicked.connect(lambda: self.add_dialog("fuel"))
        self.add_ox.clicked.connect(lambda: self.add_dialog("oxidizer"))
        self.add_mix.clicked.connect(lambda: self.add_dialog("mixture"))
        self.remove.clicked.connect(self.remove_selected)
        for b in (self.add_fuel, self.add_ox, self.add_mix, self.remove):
            row.addWidget(b)
        lay.addLayout(row)
        self.table = make_table(self.COLS)
        self.table.setEditTriggers(self.table.EditTrigger.DoubleClicked | self.table.EditTrigger.EditKeyPressed
                                   | self.table.EditTrigger.AnyKeyPressed)
        self.table.itemChanged.connect(self._item_changed)
        self.table.setMinimumHeight(220)
        lay.addWidget(self.table)
        self.body.addWidget(frame)

        info, ilay = card("Стехиометрия (по данным ядра)")
        self.km0_label = QLabel("—")
        self.km0_label.setWordWrap(True)
        ilay.addWidget(self.km0_label)
        self.body.addWidget(info)
        self.body.addStretch(1)

        state.project_changed.connect(self.refresh)
        self.refresh()

    # --- заполнение
    def refresh(self) -> None:
        self._loading = True
        p = self.state.project
        self.basis.setCurrentIndex(0 if p.conditions.basis == "mass" else 1)
        self.table.setRowCount(len(p.components))
        for r, c in enumerate(p.components):
            sp = species_db.by_name(c.name)
            self.table.setItem(r, 0, ro_item(c.name))
            role = QComboBox()
            for key, text in ROLES:
                role.addItem(text, key)
            role.setCurrentIndex(max(0, role.findData(c.role)))
            role.currentIndexChanged.connect(lambda _i, row=r, w=role: self._role_changed(row, w))
            self.table.setCellWidget(r, 1, role)
            self.table.setItem(r, 2, QTableWidgetItem(fmt(c.amount)))
            self.table.setItem(r, 3, QTableWidgetItem(fmt(c.t0)))
            self.table.setItem(r, 4, ro_item(sp.formula_text if sp else "—"))
            self.table.setItem(r, 5, ro_item(sp.phase_name if sp else "—"))
        self._loading = False
        self.update_stoich()

    def update_stoich(self) -> None:
        p = self.state.project
        try:
            sess = CeaSession(p.propellant(), p.products())
        except InputError as exc:
            self.km0_label.setText(f"Стехиометрическое соотношение не определено: {exc}")
            self.km0_label.setObjectName("Warn")
        else:
            if sess.is_mixture:
                self.km0_label.setText("Состав задан смесью целиком: доли компонентов относятся ко всей смеси, "
                                       "Kм⁰, Kм и α не определяются.")
            else:
                self.km0_label.setText(
                    f"Kм⁰ = {fmt(sess.km0)} — стехиометрическое массовое соотношение компонентов "
                    "(α = 1, по валентностям элементов в ядре NASA CEA). α = Kм / Kм⁰.")
            self.km0_label.setObjectName("")
        self.km0_label.style().unpolish(self.km0_label)
        self.km0_label.style().polish(self.km0_label)

    # --- действия
    def add_dialog(self, role: str) -> None:
        dlg = SpeciesDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected():
            self.add_species(dlg.selected().name, role)

    def add_species(self, name: str, role: str) -> None:
        sp = species_db.by_name(name)
        if sp is None:
            self.state.message.emit(f"Вещество «{name}» не найдено в базе NASA CEA.")
            return
        if any(c.name == name for c in self.state.project.components):
            self.state.message.emit(f"«{name}» уже есть в составе топлива.")
            return
        self.state.project.components.append(ComponentSpec(name, role, 100.0, default_t0(sp)))
        self.state.touch()
        self.refresh()

    def remove_selected(self) -> None:
        r = self.table.currentRow()
        if 0 <= r < len(self.state.project.components):
            del self.state.project.components[r]
            self.state.touch()
            self.refresh()

    def _basis_changed(self) -> None:
        if not self._loading:
            self.state.project.conditions.basis = self.basis.currentData()
            self.state.touch()
            self.update_stoich()

    def _role_changed(self, row: int, w: QComboBox) -> None:
        if not self._loading:
            self.state.project.components[row].role = w.currentData()
            self.state.touch()
            self.update_stoich()

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        r, c = item.row(), item.column()
        comp = self.state.project.components[r]
        try:
            v = parse_number(item.text())
            if c == 2:
                if v <= 0:
                    raise InputError("Доля должна быть положительной.")
                comp.amount = v
            elif c == 3:
                if v <= 0:
                    raise InputError("Температура должна быть больше 0 К.")
                comp.t0 = v
        except InputError as exc:
            self.state.message.emit(str(exc))
            self._loading = True
            item.setText(fmt(comp.amount if c == 2 else comp.t0))
            self._loading = False
            return
        self.state.touch()
        self.update_stoich()
