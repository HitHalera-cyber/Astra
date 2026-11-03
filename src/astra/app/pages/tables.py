"""Раздел «Таблицы результатов»: сортировка, поиск, фильтр и экспорт (CSV, XLSX, отчёт PDF/HTML)."""

from __future__ import annotations

import math
from pathlib import Path
import tempfile

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMenu, QPushButton, QTableView)

from astra.projects import datasets as D
from astra.projects import export as E

from ..widgets import Page, card, fmt
from .plots import SOURCE_TITLES

SORT_ROLE = Qt.ItemDataRole.UserRole + 1


class DatasetModel(QAbstractTableModel):
    def __init__(self, ds: D.Dataset | None = None, parent=None):
        super().__init__(parent)
        self.ds = ds
        self._status = None

    def set_dataset(self, ds: D.Dataset | None) -> None:
        self.beginResetModel()
        self.ds = ds
        keys = [c.key for c in ds.columns] if ds else []
        self._status = keys.index("status") if "status" in keys else None
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if self.ds is None or parent.isValid() else len(self.ds.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if self.ds is None or parent.isValid() else len(self.ds.columns)

    def failed(self, row: int) -> bool:
        return self._status is not None and str(self.ds.rows[row][self._status]).startswith("нет")

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.ds is None:
            return None
        c = self.ds.columns[index.column()]
        v = self.ds.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return fmt(c.display(v)) if c.kind == D.NUMBER else str(v)
        if role == SORT_ROLE:
            if c.kind == D.NUMBER:
                # NaN — в конец при сортировке по возрастанию
                return math.inf if v is None or math.isnan(v) else float(c.display(v))
            return str(v)
        if role == Qt.ItemDataRole.TextAlignmentRole and c.kind == D.NUMBER:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and self.failed(index.row()):
            return QBrush(QColor("#e5534b"))
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(v) if c.key == "status" else c.title
        return None

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if self.ds is None:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self.ds.columns[section].label
            if role == Qt.ItemDataRole.ToolTipRole:
                return self.ds.columns[section].title
        elif role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None


class DatasetFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.only_ok = False
        self.setSortRole(SORT_ROLE)

    def set_filter(self, text: str, only_ok: bool) -> None:
        modern = hasattr(self, "beginFilterChange")   # Qt 6.10+: invalidateFilter() устарел
        if modern:
            self.beginFilterChange()
        self.text = text.strip().lower().replace(".", ",")
        self.only_ok = only_ok
        if modern:
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        m: DatasetModel = self.sourceModel()
        if m.ds is None:
            return False
        if self.only_ok and m.failed(row):
            return False
        if not self.text:
            return True
        for col in range(m.columnCount()):
            if self.text in str(m.data(m.index(row, col))).lower():
                return True
        return False


class TablesPage(Page):
    title = "Таблицы результатов"
    hint = ("Сводные таблицы по последним расчётам текущего сеанса. Щелчок по заголовку — сортировка, строка "
            "поиска ищет по всем столбцам, «Столбцы» — выбор показываемых величин. CSV и XLSX сохраняют "
            "таблицу в том виде, как она показана (сортировка, фильтр, столбцы); отчёт включает исходные "
            "данные проекта, все таблицы и текущий график.")

    def __init__(self, state, plot_image=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.plot_image = plot_image      # функция: путь PNG → сохранить текущий график (или None)
        self.data: dict[str, D.Dataset] = {}
        self.hidden: dict[str, set[str]] = {}

        frame, lay = card()
        row = QHBoxLayout()
        row.addWidget(QLabel("Таблица:"))
        self.source = QComboBox()
        self.source.currentIndexChanged.connect(self._source_changed)
        row.addWidget(self.source, 2)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по всем столбцам…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        row.addWidget(self.search, 2)
        self.only_ok = QCheckBox("только сошедшиеся")
        self.only_ok.toggled.connect(self._filter)
        row.addWidget(self.only_ok)
        self.cols_btn = QPushButton("Столбцы")
        self.cols_menu = QMenu(self)
        self.cols_btn.setMenu(self.cols_menu)
        row.addWidget(self.cols_btn)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        row.addWidget(self.count, 1)
        self.csv_btn = QPushButton("CSV…")
        self.xlsx_btn = QPushButton("XLSX…")
        self.xlsx_all_btn = QPushButton("XLSX: все таблицы…")
        self.pdf_btn = QPushButton("Отчёт PDF…")
        self.html_btn = QPushButton("Отчёт HTML…")
        for b, fn in ((self.csv_btn, self.csv_dialog), (self.xlsx_btn, lambda: self.xlsx_dialog(False)),
                      (self.xlsx_all_btn, lambda: self.xlsx_dialog(True)), (self.pdf_btn, lambda: self.report_dialog("pdf")),
                      (self.html_btn, lambda: self.report_dialog("html"))):
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self.body.addWidget(frame)

        self.model = DatasetModel()
        self.proxy = DatasetFilter()
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.view.setMinimumHeight(620)
        self.body.addWidget(self.view, 1)

        # пришедший результат сразу показывается
        for sig, key in ((state.result_ready, "thermo"), (state.study_ready, "study"),
                         (state.nozzle_ready, "nozzle"), (state.isp_ready, "isp")):
            sig.connect(lambda *_, k=key: self.reload(k))
        state.project_changed.connect(lambda: self.reload())
        self.reload()

    # ------------------------------------------------------------ данные
    def reload(self, focus: str | None = None) -> None:
        self.data = D.collect(self.state)
        cur = focus or self.source.currentData()
        self.source.blockSignals(True)
        self.source.clear()
        for key, ds in self.data.items():
            self.source.addItem(f"{SOURCE_TITLES[key]} — {ds.name}" if key == "thermo" else SOURCE_TITLES[key], key)
        idx = self.source.findData(cur)
        self.source.setCurrentIndex(idx if idx >= 0 else self.source.count() - 1)
        self.source.blockSignals(False)
        has = bool(self.data)
        for b in (self.csv_btn, self.xlsx_btn, self.xlsx_all_btn, self.pdf_btn, self.html_btn, self.cols_btn):
            b.setEnabled(has)
        self._source_changed()

    def show_source(self, key: str) -> None:
        idx = self.source.findData(key)
        if idx >= 0:
            self.source.setCurrentIndex(idx)

    def dataset(self) -> D.Dataset | None:
        return self.data.get(self.source.currentData())

    def _source_changed(self) -> None:
        ds = self.dataset()
        self.model.set_dataset(ds)
        self.cols_menu.clear()
        key = self.source.currentData()
        hidden = self.hidden.setdefault(key, set()) if key else set()
        if ds is not None:
            for j, c in enumerate(ds.columns):
                act = self.cols_menu.addAction(c.label)
                act.setCheckable(True)
                act.setChecked(c.key not in hidden)
                act.toggled.connect(lambda on, k=c.key, col=j: self._toggle_column(k, col, on))
                self.view.setColumnHidden(j, c.key in hidden)
        self._filter()

    def _toggle_column(self, key: str, col: int, on: bool) -> None:
        hidden = self.hidden.setdefault(self.source.currentData(), set())
        (hidden.discard if on else hidden.add)(key)
        self.view.setColumnHidden(col, not on)

    def _filter(self, *_) -> None:
        self.proxy.set_filter(self.search.text(), self.only_ok.isChecked())
        ds = self.dataset()
        if ds is None:
            self.count.setText("Нет рассчитанных данных: выполните расчёт или исследование.")
            return
        bad = sum(self.model.failed(i) for i in range(self.model.rowCount()))
        text = f"Строк: {self.proxy.rowCount()} из {len(ds.rows)}"
        if bad:
            text += f"; без результата ядра: {bad} (выделены, причина — в столбце «Сходимость»)"
        self.count.setText(text + ".")

    def view_selection(self) -> tuple[list[str], list[int]]:
        """Показанные столбцы и строки — в порядке сортировки."""
        ds = self.dataset()
        cols = [c.key for j, c in enumerate(ds.columns) if not self.view.isColumnHidden(j)]
        rows = [self.proxy.mapToSource(self.proxy.index(r, 0)).row() for r in range(self.proxy.rowCount())]
        return cols, rows

    # ------------------------------------------------------------ экспорт
    def _ask(self, title: str, default: str, filt: str, ext: str) -> str | None:
        name, _ = QFileDialog.getSaveFileName(self, title, default, filt)
        if not name:
            return None
        return name if name.lower().endswith(ext) else name + ext

    def export_csv(self, path) -> Path:
        cols, rows = self.view_selection()
        return E.to_csv(self.dataset(), path, columns=cols, rows=rows)

    def export_xlsx(self, path, all_tables: bool) -> Path:
        proj = self.state.project.name
        if all_tables:
            return E.to_xlsx(list(self.data.values()), path, project_name=proj)
        ds = self.dataset()
        return E.to_xlsx([ds], path, project_name=proj, selections={ds.name: self.view_selection()})

    def csv_dialog(self) -> None:
        name = self._ask("Сохранить таблицу CSV", "таблица.csv", "Таблица CSV (*.csv)", ".csv")
        if name:
            self.export_csv(name)
            self.state.message.emit(f"Таблица сохранена: {name}")

    def xlsx_dialog(self, all_tables: bool) -> None:
        name = self._ask("Сохранить книгу Excel", "результаты.xlsx", "Книга Excel (*.xlsx)", ".xlsx")
        if name:
            self.export_xlsx(name, all_tables)
            self.state.message.emit(f"Книга Excel сохранена: {name}")

    def report_html(self, image: Path | None = None, image_src: str | None = None) -> str:
        """HTML отчёта; image — куда сохранить PNG текущего графика, image_src — ссылка на него в отчёте."""
        sections = []
        for key, ds in self.data.items():
            body = E.transpose(ds) if key == "thermo" else ds
            sections.append((SOURCE_TITLES[key] + ("" if key != "thermo" else f" — {ds.name}"), body))
        if image is not None and self.plot_image is not None and self.data and self.plot_image(image):
            sections.append(("График", ("image", image_src or image.as_uri(), 640)))
        return E.report_html(f"Отчёт: {self.state.project.name}", sections, project_name=self.state.project.name,
                             inputs=E.project_inputs(self.state.project))

    def export_report(self, path, kind: str) -> Path:
        path = Path(path)
        if kind == "html":
            img = path.with_name(path.stem + "-график.png")
            path.write_text(self.report_html(img, img.name), encoding="utf-8")
            return path
        img = Path(tempfile.mkdtemp()) / "график.png"
        html = self.report_html(img)
        doc = QTextDocument()
        if img.exists():
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(img.as_uri()), QImage(str(img)))
        doc.setHtml(html)
        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Landscape)
        writer.setResolution(150)
        writer.setTitle(f"Отчёт: {self.state.project.name}")
        writer.setCreator("Astra (NASA CEA)")
        doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size().toSizeF())
        doc.print_(writer)
        return path

    def report_dialog(self, kind: str) -> None:
        filt = "Документ PDF (*.pdf)" if kind == "pdf" else "Страница HTML (*.html)"
        name = self._ask("Сохранить отчёт", f"отчёт.{kind}", filt, f".{kind}")
        if name:
            self.export_report(name, kind)
            self.state.message.emit(f"Отчёт сохранён: {name}")
