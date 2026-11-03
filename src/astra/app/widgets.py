"""Общие элементы интерфейса: поля величин с обозначениями, карточки, форматирование."""

from __future__ import annotations

import math
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView)

from astra.core import InputError, Quantity, q


def parse_number(text: str) -> float:
    t = text.strip().replace(" ", "").replace(" ", "").replace(",", ".").replace("−", "-")
    if not t:
        raise InputError("Значение не задано.")
    try:
        return float(t)
    except ValueError:
        raise InputError(f"«{text}» — не число.") from None


def parse_list(text: str) -> list[float]:
    parts = [p for p in text.replace(";", " ").replace("\n", " ").split() if p]
    return [parse_number(p) for p in parts]


def fmt(value: float | None, digits: int = 6) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    if value == 0:
        return "0"
    a = abs(value)
    if 1e-3 <= a < 1e7:
        s = f"{value:.{digits}g}"
    else:
        s = f"{value:.{digits - 1}e}"
    return s.replace(".", ",")


def fmt_list(values: Iterable[float]) -> str:
    return "; ".join(fmt(v) for v in values)


def tooltip(qt: Quantity) -> str:
    lines = [f"<b>{qt.symbol}</b> — {qt.name}"]
    if qt.meaning:
        lines.append(qt.meaning)
    if qt.description:
        lines.append(f"<i>{qt.description}</i>")
    if qt.unit:
        lines.append(f"Единица: {qt.unit}")
    lo = None if math.isinf(qt.lower) else qt.to_display(qt.lower)
    hi = None if math.isinf(qt.upper) else qt.to_display(qt.upper)
    if lo is not None or hi is not None:
        lines.append(f"Допустимые значения: {fmt(lo) if lo is not None else '−∞'} … {fmt(hi) if hi is not None else '+∞'}")
    return "<br>".join(lines)


class QuantityField(QWidget):
    """Поле ввода величины: подпись «обозначение, единица», значение в единицах отображения.

    value() возвращает значение в СИ; некорректный ввод подсвечивается и поднимает InputError.
    """

    edited = Signal()

    def __init__(self, key: str, parent: QWidget | None = None, *, allow_empty: bool = False):
        super().__init__(parent)
        self.quantity = q(key)
        self.allow_empty = allow_empty
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(self.quantity.label())
        self.label.setMinimumWidth(90)
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(110)
        self.edit.setToolTip(tooltip(self.quantity))
        self.label.setToolTip(tooltip(self.quantity))
        self.edit.editingFinished.connect(self._changed)
        lay.addWidget(self.label)
        lay.addWidget(self.edit, 1)

    def _changed(self) -> None:
        try:
            self.value()
            self._mark(False)
        except InputError as exc:
            self._mark(True, str(exc))
        self.edited.emit()

    def _mark(self, bad: bool, msg: str = "") -> None:
        self.edit.setProperty("invalid", bad)
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)
        self.edit.setToolTip((f"<span style='color:#e5534b'>{msg}</span><br>" if bad else "") + tooltip(self.quantity))

    def value(self) -> float | None:
        text = self.edit.text()
        if not text.strip() and self.allow_empty:
            return None
        v = self.quantity.from_display(parse_number(text))
        self.quantity.check(v)
        return v

    def set_value(self, si: float | None) -> None:
        self.edit.setText("" if si is None else fmt(self.quantity.to_display(si), 8))
        self._mark(False)


class ListField(QWidget):
    """Список значений одной величины через «;» (например, несколько ε)."""

    edited = Signal()

    def __init__(self, key: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.quantity = q(key)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(self.quantity.label())
        self.label.setMinimumWidth(90)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("значения через «;»")
        self.edit.setToolTip(tooltip(self.quantity))
        self.label.setToolTip(tooltip(self.quantity))
        self.edit.editingFinished.connect(self.edited.emit)
        lay.addWidget(self.label)
        lay.addWidget(self.edit, 1)

    def values(self) -> list[float]:
        vals = [self.quantity.from_display(v) for v in parse_list(self.edit.text())]
        for v in vals:
            self.quantity.check(v)
        return vals

    def set_values(self, si: Iterable[float]) -> None:
        self.edit.setText(fmt_list(self.quantity.to_display(v) for v in si))


class SpeciesListField(QWidget):
    """Список веществ базы NASA CEA через пробел или «;» (only, omit, insert)."""

    edited = Signal()

    def __init__(self, label: str, tip: str, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.label.setMinimumWidth(90)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("имена веществ базы через пробел, например: H2O CO2 OH")
        self.edit.setToolTip(tip)
        self.label.setToolTip(tip)
        self.edit.editingFinished.connect(self.edited.emit)
        lay.addWidget(self.label)
        lay.addWidget(self.edit, 1)

    def values(self) -> list[str]:
        from astra.core import species_db
        names = [n for n in self.edit.text().replace(";", " ").split() if n]
        unknown = [n for n in names if species_db.by_name(n) is None]
        if unknown:
            raise InputError(f"{self.label.text()}: нет в базе NASA CEA: {', '.join(unknown)}.")
        return names

    def set_values(self, names: Iterable[str]) -> None:
        self.edit.setText(" ".join(names))


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    if title:
        t = QLabel(title)
        t.setObjectName("CardTitle")
        lay.addWidget(t)
    return frame, lay


class Page(QWidget):
    """Раздел приложения: заголовок, пояснение и прокручиваемое содержимое."""

    title = ""
    hint = ""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(24, 20, 24, 20)
        self.body.setSpacing(12)
        t = QLabel(self.title)
        t.setObjectName("PageTitle")
        self.body.addWidget(t)
        if self.hint:
            h = QLabel(self.hint)
            h.setObjectName("PageHint")
            h.setWordWrap(True)
            self.body.addWidget(h)

    def refresh(self) -> None:
        """Обновить содержимое из текущего проекта (вызывается при открытии раздела)."""


def make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return t


def ro_item(text: str, align_right: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if align_right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return it
