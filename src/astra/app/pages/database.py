"""Раздел «База веществ»."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter

from astra.core import species_db

from ..widgets import Page, card, fmt, make_table, ro_item


class DatabasePage(Page):
    title = "База веществ"
    hint = ("Термодинамическая база NASA CEA (NASA TP-2002-211556): 2111 записей. "
            "Поиск по имени, формуле и описанию; выбранное вещество можно добавить в состав топлива.")

    def __init__(self, state, propellant_page, parent=None):
        super().__init__(parent)
        self.state = state
        self.propellant_page = propellant_page
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск: H2O, Al(cr), RP-1, hydrazine…")
        self.search.textChanged.connect(self.fill)
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        row.addWidget(self.search, 1)
        row.addWidget(self.count)
        self.body.addLayout(row)

        self.table = make_table(["Вещество", "Формула", "Фаза", "μ, г/моль", "ΔHf°, кДж/моль", "T, К", "Раздел"])
        self.table.setMinimumHeight(380)
        self.table.itemSelectionChanged.connect(self.show_details)
        self.body.addWidget(self.table, 1)

        frame, lay = card("Сведения о веществе")
        self.details = QLabel("Выберите вещество в таблице.")
        self.details.setWordWrap(True)
        lay.addWidget(self.details)
        btns = QHBoxLayout()
        self.as_fuel = QPushButton("Добавить как горючее")
        self.as_ox = QPushButton("Добавить как окислитель")
        self.as_fuel.clicked.connect(lambda: self._add("fuel"))
        self.as_ox.clicked.connect(lambda: self._add("oxidizer"))
        btns.addWidget(self.as_fuel)
        btns.addWidget(self.as_ox)
        btns.addStretch(1)
        lay.addLayout(btns)
        self.body.addWidget(frame)
        self.fill()

    def fill(self) -> None:
        found = species_db.search(self.search.text(), limit=500)
        total = len(species_db.search(self.search.text()))
        self.count.setText(f"Найдено: {total}" + (" (показаны первые 500)" if total > 500 else ""))
        self.table.setRowCount(len(found))
        for r, s in enumerate(found):
            temp = fmt(s.t_assigned) if s.t_assigned is not None else f"{fmt(s.t_min)}…{fmt(s.t_max)}"
            cells = [s.name, s.formula_text, s.phase_name, fmt(s.molar_mass), fmt(s.hf / 1000), temp,
                     "исходное вещество" if s.reactant_only else "продукт и исходное"]
            for c, text in enumerate(cells):
                self.table.setItem(r, c, ro_item(text, c in (3, 4)))
        self.as_fuel.setEnabled(False)
        self.as_ox.setEnabled(False)

    def current(self) -> species_db.Species | None:
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        return species_db.by_name(it.text()) if it else None

    def show_details(self) -> None:
        s = self.current()
        self.as_fuel.setEnabled(s is not None)
        self.as_ox.setEnabled(s is not None)
        if s is None:
            return
        if s.t_assigned is not None:
            t = f"задано при одной температуре T = {fmt(s.t_assigned)} К; энтальпия при этой температуре {fmt(s.hf / 1000)} кДж/моль"
        else:
            t = ("интервалы аппроксимации: " + "; ".join(f"{fmt(a)}…{fmt(b)} К" for a, b in s.t_ranges)
                 + f"; энтальпия образования при 298,15 К {fmt(s.hf / 1000)} кДж/моль")
        self.details.setText(
            f"<b>{s.name}</b> — {s.formula_text}, {s.phase_name}, μ = {fmt(s.molar_mass)} г/моль.<br>"
            f"{t}.<br>Источник данных: {s.comment or '—'} (код {s.ref_code}).")

    def _add(self, role: str) -> None:
        s = self.current()
        if s:
            self.propellant_page.add_species(s.name, role)
            self.state.message.emit(f"«{s.name}» добавлено в состав топлива.")
