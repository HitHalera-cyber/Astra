"""Требования ТЗ к интерфейсу в целом: каждая кнопка что-то делает, обозначения отечественные,
все 12 разделов — рабочие, неверный ввод не роняет программу."""

import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import SIGNAL, Qt  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QHeaderView, QLabel, QLineEdit, QListWidget,  # noqa: E402
                               QPushButton, QTableView, QTableWidget, QTabWidget)

from astra.core import QUANTITIES, q  # noqa: E402

from test_gui import app, window  # noqa: E402,F401  (фикстуры)

FORBIDDEN = re.compile(r"γ|gamma|Gamma|\bO/F\b|\bIsp\b|\bphi\b|φ")


def visible_texts(root):
    """Все тексты интерфейса: подписи, кнопки, подсказки, заголовки таблиц, пункты списков."""
    out = []
    for w in root.findChildren(QLabel) + root.findChildren(QAbstractButton) + root.findChildren(QLineEdit):
        for t in (getattr(w, "text", lambda: "")(), w.toolTip(), getattr(w, "placeholderText", lambda: "")()):
            if t:
                out.append((type(w).__name__, t))
    for c in root.findChildren(QComboBox):
        out += [("QComboBox", c.itemText(i)) for i in range(c.count())]
    for lw in root.findChildren(QListWidget):
        out += [("QListWidget", lw.item(i).text()) for i in range(lw.count())]
        out += [("QListWidget", lw.item(i).toolTip()) for i in range(lw.count())]
    for t in root.findChildren(QTableWidget):
        for c in range(t.columnCount()):
            h = t.horizontalHeaderItem(c)
            if h is not None:
                out.append(("header", h.text()))
        for r in range(t.rowCount()):
            for c in range(min(t.columnCount(), 2)):
                it = t.item(r, c)
                if it is not None:
                    out.append(("cell", it.text()))
    for v in root.findChildren(QTableView):
        m = v.model()
        if m is not None:
            out += [("header", str(m.headerData(c, Qt.Orientation.Horizontal))) for c in range(m.columnCount())]
    for tw in root.findChildren(QTabWidget):
        out += [("tab", tw.tabText(i)) for i in range(tw.count())]
    return out


def run_everything(app, window):
    st = window.state
    t = window.pages["thermo"]
    t.run()
    t.thread.wait(60000)
    for key in ("parametric", "nozzle", "isp"):
        page = window.pages[key]
        page.run()
        page.thread.wait(120000)
    app.processEvents()


def test_all_sections_are_working_pages(app, window):
    from astra.app.main_window import SECTIONS
    from astra.app.pages.basic import PlannedPage
    assert len(SECTIONS) == 12
    for key, _ in SECTIONS:
        assert not isinstance(window.pages[key], PlannedPage), key


def test_every_button_has_an_action(app, window):
    run_everything(app, window)
    dead = []
    for key, page in window.pages.items():
        for b in page.findChildren(QPushButton):
            if b.menu() is not None:
                continue
            if b.receivers(SIGNAL("clicked()")) + b.receivers(SIGNAL("clicked(bool)")) == 0:
                dead.append(f"{key}: «{b.text()}»")
    assert not dead, "кнопки без действия: " + ", ".join(dead)


def test_interface_uses_russian_notation(app, window):
    run_everything(app, window)
    bad = []
    for key, page in window.pages.items():
        for kind, text in visible_texts(page):
            if FORBIDDEN.search(text):
                bad.append(f"{key} / {kind}: {text[:80]}")
    assert not bad, "иностранные обозначения в интерфейсе:\n" + "\n".join(bad)


def test_notation_table():
    assert q("k").symbol == "k"
    assert q("Km").symbol == "Kм" and q("alpha").symbol == "α" and q("Km").name != q("alpha").name
    assert q("i").symbol == "i" and "статич" in q("i").description.lower()
    assert q("H").symbol == "H" and "W²/2" in (q("H").meaning + q("H").description)
    for key, qt in QUANTITIES.items():
        assert not FORBIDDEN.search(qt.symbol + qt.name + qt.meaning + qt.unit + qt.description), key


@pytest.mark.parametrize("calc", ["rocket", "TP", "HP", "SP", "TV", "UV", "SV", "shock", "detonation"])
def test_bad_input_is_reported_not_crashing(app, window, calc):
    """Недопустимые исходные данные — сообщение об ошибке, а не падение или «результат»."""
    st = window.state
    c = st.project.conditions
    c.calc = calc
    c.pk = -1.0
    c.t = -5.0
    c.v = -1.0
    c.t1, c.p1 = [-1.0], [-1.0]
    c.u1, c.mach1 = [-1.0], [-1.0]
    st.touch()
    t = window.pages["thermo"]
    t.run()
    if t.thread is not None:
        t.thread.wait(60000)
    app.processEvents()
    assert t.status.objectName() == "Bad", t.status.text()
    assert st.last_result is None
