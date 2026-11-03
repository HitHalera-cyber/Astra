"""Раздел «Графики»: интерактивные графики и цветовые карты по расчётным данным (PyQtGraph)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton)

from astra.projects import datasets as D

from ..widgets import Page, card, fmt

SOURCE_TITLES = {"thermo": "Термодинамический расчёт", "study": "Параметрическое исследование",
                 "nozzle": "Исследование сопла", "isp": "Удельный импульс", "isp_optima": "Максимумы Iуд"}
MODES = {"lines": "Линии", "map": "Цветовая карта (поверхность)"}
# серия цветов, различимых в тёмной и светлой темах
PALETTE = ["#4c8dff", "#e5534b", "#3fb27f", "#e0a43a", "#a371f7", "#39c5cf", "#f778ba", "#8b949e",
           "#d29922", "#2ea043"]
THEMES = {"dark": ("#1b1e23", "#e4e7eb"), "light": ("#ffffff", "#1c2127")}
MAX_CATEGORIES = 16


def defaults(key: str, ds: D.Dataset) -> tuple[str | None, list[str], list[str], tuple[str, object] | None]:
    """Оси по умолчанию: X, список Y, группировка серий, фильтр."""
    keys = [c.key for c in ds.columns]
    num = [c.key for c in ds.numeric()]
    if key == "isp":
        return "Km", ["isp_amb"], ["model", "eps"], ("pn", ds.column("pn")[0]) if ds.rows else None
    if key == "nozzle":
        pn = sorted(set(ds.column("pn")))
        return "eps", ["isp_amb"], ["model"], ("pn", pn[-1]) if pn else None
    if key == "isp_optima":
        return "eps", ["isp_amb"], ["model"], None
    if key == "study":
        axes = [c.key for c in ds.columns if c.key in num][:2]
        y = next((k for k in ("isp_vac", "isp", "t") if k in keys and k not in axes), num[-1] if num else None)
        group = [axes[1]] if len(axes) > 1 else []
        flt = None
        if "section" in keys:
            sec = ds.column("section")
            flt = ("section", sec[-1] if sec else None)
        return axes[0] if axes else None, [y] if y else [], group, flt
    if key == "thermo":
        if "eps" in num:
            return "eps", ["t", "p"] if "p" in num else ["t"], [], None
        return (num[0] if num else None), num[1:2], [], None
    return (num[0] if num else None), num[1:2], [], None


def categorical(ds: D.Dataset) -> list[D.Column]:
    """Столбцы, по которым можно группировать серии и фильтровать: текстовые и с немногими значениями."""
    out = []
    for c in ds.columns:
        if c.key == "status":
            continue
        vals = ds.column(c.key)
        uniq = {v for v in vals if not (isinstance(v, float) and math.isnan(v))}
        if 1 < len(uniq) <= MAX_CATEGORIES and (c.kind == D.TEXT or len(uniq) < len(vals)):
            out.append(c)
    return out


def _edges(v: list[float], log: bool) -> np.ndarray:
    """Границы ячеек вокруг узлов: середины между узлами (геометрические — для логарифмической сетки)."""
    a = np.asarray(v, dtype=float)
    if log and np.all(a > 0):
        la = np.log(a)
        mid = (la[1:] + la[:-1]) / 2
        return np.exp(np.concatenate([[la[0] - (mid[0] - la[0])], mid, [la[-1] + (la[-1] - mid[-1])]]))
    mid = (a[1:] + a[:-1]) / 2
    return np.concatenate([[a[0] - (mid[0] - a[0])], mid, [a[-1] + (a[-1] - mid[-1])]])


def _value_text(c: D.Column, v) -> str:
    if c.kind == D.TEXT:
        return str(v)
    return f"{c.label.split(',')[0]} = {fmt(c.display(v))}"


class PlotsPage(Page):
    title = "Графики"
    hint = ("Графики строятся по последним расчётам текущего сеанса — только по значениям, полученным от ядра "
            "NASA CEA. Несошедшиеся точки не соединяются линией и не заменяются: на графике остаётся разрыв. "
            "Колесо мыши — масштаб, правая кнопка — меню масштабирования и экспорта PyQtGraph.")

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.data: dict[str, D.Dataset] = {}
        self._theme = "dark"
        self._loading = False

        frame, lay = card("Данные и оси")
        g = QGridLayout()
        self.source = QComboBox()
        self.mode = QComboBox()
        for k, t in MODES.items():
            self.mode.addItem(t, k)
        self.x = QComboBox()
        self.y2 = QComboBox()        # ось Y для цветовой карты
        self.z = QComboBox()         # величина цвета
        self.ys = QListWidget()
        self.ys.setFlow(QListWidget.Flow.LeftToRight)
        self.ys.setWrapping(True)
        self.ys.setMaximumHeight(70)
        self.group1, self.group2 = QComboBox(), QComboBox()
        self.filter_key, self.filter_value = QComboBox(), QComboBox()
        self.log_x, self.log_y = QCheckBox("лог. шкала X"), QCheckBox("лог. шкала Y")
        self.markers = QCheckBox("маркеры точек")
        self.markers.setChecked(True)
        g.addWidget(QLabel("Источник:"), 0, 0)
        g.addWidget(self.source, 0, 1)
        g.addWidget(QLabel("Вид:"), 0, 2)
        g.addWidget(self.mode, 0, 3)
        g.addWidget(QLabel("Ось X:"), 1, 0)
        g.addWidget(self.x, 1, 1)
        self.y2_label, self.z_label = QLabel("Ось Y:"), QLabel("Цвет:")
        g.addWidget(self.y2_label, 1, 2)
        g.addWidget(self.y2, 1, 3)
        g.addWidget(self.z_label, 1, 4)
        g.addWidget(self.z, 1, 5)
        self.ys_label = QLabel("Величины по Y:")
        g.addWidget(self.ys_label, 2, 0, Qt.AlignmentFlag.AlignTop)
        g.addWidget(self.ys, 2, 1, 1, 5)
        self.group_label = QLabel("Серии по:")
        g.addWidget(self.group_label, 3, 0)
        g.addWidget(self.group1, 3, 1)
        g.addWidget(QLabel("и по:"), 3, 2)
        g.addWidget(self.group2, 3, 3)
        g.addWidget(QLabel("Только:"), 4, 0)
        g.addWidget(self.filter_key, 4, 1)
        g.addWidget(QLabel("="), 4, 2, Qt.AlignmentFlag.AlignRight)
        g.addWidget(self.filter_value, 4, 3)
        opts = QHBoxLayout()
        for w in (self.log_x, self.log_y, self.markers):
            opts.addWidget(w)
        opts.addStretch(1)
        g.addLayout(opts, 5, 1, 1, 5)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        g.setColumnStretch(5, 1)
        lay.addLayout(g)
        self.body.addWidget(frame)

        frame, lay = card()
        row = QHBoxLayout()
        self.info = QLabel("Нет рассчитанных данных: выполните расчёт или исследование.")
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        self.cursor = QLabel("")
        self.cursor.setObjectName("Muted")
        self.png_btn = QPushButton("Сохранить PNG…")
        self.svg_btn = QPushButton("Сохранить SVG…")
        self.png_btn.clicked.connect(lambda: self.save_dialog("png"))
        self.svg_btn.clicked.connect(lambda: self.save_dialog("svg"))
        row.addWidget(self.info, 1)
        row.addWidget(self.cursor)
        row.addWidget(self.png_btn)
        row.addWidget(self.svg_btn)
        lay.addLayout(row)
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setMinimumHeight(560)
        self.plot = self.glw.addPlot(row=0, col=0)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.legend = self.plot.addLegend(offset=(10, 10))
        self.colorbar: pg.ColorBarItem | None = None
        self.image: pg.ImageItem | None = None
        lay.addWidget(self.glw, 1)
        self.body.addWidget(frame, 1)
        self.proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=30, slot=self._mouse)

        self.source.currentIndexChanged.connect(self._source_changed)
        for w in (self.mode, self.x, self.y2, self.z, self.group1, self.group2, self.filter_value):
            w.currentIndexChanged.connect(self.redraw)
        self.filter_key.currentIndexChanged.connect(self._filter_key_changed)
        self.ys.itemChanged.connect(lambda *_: self.redraw())
        for w in (self.log_x, self.log_y, self.markers):
            w.toggled.connect(lambda *_: self.redraw())
        # пришедший результат сразу показывается
        for sig, key in ((state.result_ready, "thermo"), (state.study_ready, "study"),
                         (state.nozzle_ready, "nozzle"), (state.isp_ready, "isp")):
            sig.connect(lambda *_, k=key: self.reload(k))
        state.project_changed.connect(lambda: self.reload())
        self.reload()

    # ------------------------------------------------------------ данные
    def reload(self, focus: str | None = None) -> None:
        self.data = D.collect(self.state)
        current = focus or self.source.currentData()
        self._loading = True
        self.source.clear()
        for key, ds in self.data.items():
            self.source.addItem(f"{SOURCE_TITLES[key]} — {ds.name}" if key == "thermo" else SOURCE_TITLES[key], key)
        self._loading = False
        has = bool(self.data)
        for w in (self.png_btn, self.svg_btn):
            w.setEnabled(has)
        if not has:
            self.plot.clear()
            self._drop_image()
            self.info.setText("Нет рассчитанных данных: выполните расчёт или исследование.")
            return
        idx = self.source.findData(current)
        # новый результат показывается сразу: последний пришедший источник выбирается, если прежний пропал
        self.source.setCurrentIndex(idx if idx >= 0 else self.source.count() - 1)
        self._source_changed()

    def show_source(self, key: str) -> None:
        idx = self.source.findData(key)
        if idx >= 0:
            self.source.setCurrentIndex(idx)

    def dataset(self) -> D.Dataset | None:
        return self.data.get(self.source.currentData())

    def _source_changed(self) -> None:
        if self._loading:
            return
        ds = self.dataset()
        if ds is None:
            return
        self._loading = True
        x, ys, groups, flt = defaults(self.source.currentData(), ds)
        num = ds.numeric()
        for combo in (self.x, self.y2, self.z):
            combo.clear()
            for c in num:
                combo.addItem(c.label, c.key)
        self.x.setCurrentIndex(max(0, self.x.findData(x)))
        self.y2.setCurrentIndex(min(1, self.y2.count() - 1))
        self.z.setCurrentIndex(max(0, self.z.findData(ys[0] if ys else None)))
        self.ys.clear()
        for c in num:
            it = QListWidgetItem(c.label)
            it.setData(Qt.ItemDataRole.UserRole, c.key)
            it.setToolTip(c.title)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if c.key in ys else Qt.CheckState.Unchecked)
            self.ys.addItem(it)
        cats = categorical(ds)
        for combo in (self.group1, self.group2, self.filter_key):
            combo.clear()
            combo.addItem("—", None)
            for c in cats:
                combo.addItem(c.label, c.key)
        for combo, key in ((self.group1, groups[0] if groups else None),
                           (self.group2, groups[1] if len(groups) > 1 else None)):
            combo.setCurrentIndex(max(0, combo.findData(key)))
        self.filter_key.setCurrentIndex(max(0, self.filter_key.findData(flt[0] if flt else None)))
        self._fill_filter_values(flt[1] if flt else None)
        if self.mode.currentData() == "map" and len(num) < 3:
            self.mode.setCurrentIndex(0)
        self._loading = False
        self.redraw()

    def _fill_filter_values(self, want=None) -> None:
        ds = self.dataset()
        key = self.filter_key.currentData()
        self.filter_value.blockSignals(True)
        self.filter_value.clear()
        if ds is not None and key is not None:
            c = ds.columns[ds.index(key)]
            seen = []
            for v in ds.column(key):
                if v not in seen and not (isinstance(v, float) and math.isnan(v)):
                    seen.append(v)
            for v in seen:
                self.filter_value.addItem(str(v) if c.kind == D.TEXT else fmt(c.display(v)), v)
            idx = next((i for i, v in enumerate(seen) if v == want), 0)
            self.filter_value.setCurrentIndex(idx)
        self.filter_value.setEnabled(key is not None)
        self.filter_value.blockSignals(False)

    def _filter_key_changed(self) -> None:
        if self._loading:
            return
        self._fill_filter_values()
        self.redraw()

    def selected_y(self) -> list[str]:
        return [self.ys.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.ys.count())
                if self.ys.item(i).checkState() == Qt.CheckState.Checked]

    def _rows(self, ds: D.Dataset) -> list[int]:
        key = self.filter_key.currentData()
        if key is None:
            return list(range(len(ds.rows)))
        want = self.filter_value.currentData()
        j = ds.index(key)
        return [i for i, r in enumerate(ds.rows) if r[j] == want]

    # ------------------------------------------------------------ рисование
    def _drop_image(self) -> None:
        if self.colorbar is not None:
            # шкала вставлена в раскладку графика (insert_in), а не в GraphicsLayoutWidget
            self.plot.layout.removeItem(self.colorbar)
            if self.colorbar.scene() is not None:
                self.colorbar.scene().removeItem(self.colorbar)
            self.colorbar = None
        if self.image is not None:
            self.plot.removeItem(self.image)
            self.image = None

    def redraw(self, *_) -> None:
        if self._loading:
            return
        ds = self.dataset()
        lines = self.mode.currentData() == "lines"
        for w in (self.ys, self.ys_label, self.group1, self.group2, self.group_label, self.markers):
            w.setEnabled(lines)
        for w in (self.y2, self.y2_label, self.z, self.z_label):
            w.setEnabled(not lines)
        self.plot.clear()
        self.legend.clear()
        self._drop_image()
        if ds is None:
            return
        if lines:
            self._draw_lines(ds)
        else:
            self._draw_map(ds)

    def _style(self, n: int) -> dict:
        color = PALETTE[n % len(PALETTE)]
        style = [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine][(n // len(PALETTE)) % 3]
        kw = {"pen": pg.mkPen(color, width=2, style=style), "connect": "finite"}
        if self.markers.isChecked():
            kw.update(symbol="o", symbolSize=6, symbolBrush=color, symbolPen=None)
        return kw

    def _draw_lines(self, ds: D.Dataset) -> None:
        xk = self.x.currentData()
        ys = [k for k in self.selected_y() if k != xk]
        if xk is None or not ys:
            self.info.setText("Выберите величину по оси X и хотя бы одну величину по оси Y.")
            return
        rows = self._rows(ds)
        gkeys = [k for k in (self.group1.currentData(), self.group2.currentData()) if k is not None]
        gkeys = list(dict.fromkeys(gkeys))
        xi = ds.index(xk)
        xc = ds.columns[xi]
        groups: dict[tuple, list[int]] = {}
        for i in rows:
            groups.setdefault(tuple(ds.rows[i][ds.index(k)] for k in gkeys), []).append(i)
        n_curve = 0
        n_bad = 0
        log_x, log_y = self.log_x.isChecked(), self.log_y.isChecked()
        skipped_log = 0
        for gval, idx in groups.items():
            idx = sorted(idx, key=lambda i: (math.isnan(ds.rows[i][xi]) if isinstance(ds.rows[i][xi], float)
                                             else False, ds.rows[i][xi]))
            x = np.array([xc.display(ds.rows[i][xi]) for i in idx], dtype=float)
            for yk in ys:
                yi = ds.index(yk)
                yc = ds.columns[yi]
                y = np.array([yc.display(ds.rows[i][yi]) for i in idx], dtype=float)
                n_bad += int(np.sum(~np.isfinite(y) & np.isfinite(x)))
                if log_x:
                    skipped_log += int(np.sum(x <= 0))
                if log_y:
                    skipped_log += int(np.sum(y <= 0))
                name = ", ".join(_value_text(ds.columns[ds.index(k)], v) for k, v in zip(gkeys, gval))
                if len(ys) > 1 or not name:
                    name = f"{yc.label}" + (f" — {name}" if name else "")
                self.plot.plot(x, y, name=name, **self._style(n_curve))
                n_curve += 1
        self.plot.setLogMode(x=log_x, y=log_y)
        self.plot.setLabel("bottom", xc.label)
        self.plot.setLabel("left", ds.columns[ds.index(ys[0])].label if len(ys) == 1 else "")
        self.plot.enableAutoRange()
        text = f"Кривых: {n_curve}; точек: {len(rows)}."
        if n_bad:
            text += f" Значений без результата ядра: {n_bad} — на графике разрывы."
        if skipped_log:
            text += f" Неположительных значений на логарифмической шкале: {skipped_log} — не показаны."
        self.info.setText(text)

    def _draw_map(self, ds: D.Dataset) -> None:
        xk, yk, zk = self.x.currentData(), self.y2.currentData(), self.z.currentData()
        if None in (xk, yk, zk) or len({xk, yk, zk}) < 3:
            self.info.setText("Для цветовой карты выберите три разные величины: X, Y и цвет.")
            return
        rows = self._rows(ds)
        xc, yc, zc = (ds.columns[ds.index(k)] for k in (xk, yk, zk))
        pts = [(xc.display(ds.rows[i][ds.index(xk)]), yc.display(ds.rows[i][ds.index(yk)]),
                zc.display(ds.rows[i][ds.index(zk)])) for i in rows]
        pts = [p for p in pts if math.isfinite(p[0]) and math.isfinite(p[1])]
        xs = sorted({p[0] for p in pts})
        yv = sorted({p[1] for p in pts})
        if len(xs) < 2 or len(yv) < 2:
            self.info.setText("Для цветовой карты нужна сетка: по X и по Y должно быть не меньше двух значений "
                              "(например, параметрическое исследование по двум величинам).")
            return
        grid = np.full((len(xs), len(yv)), np.nan)
        xi = {v: n for n, v in enumerate(xs)}
        yi = {v: n for n, v in enumerate(yv)}
        dup = 0
        for x, y, z in pts:
            if not math.isnan(grid[xi[x], yi[y]]):
                dup += 1
            grid[xi[x], yi[y]] = z
        if dup:
            self.info.setText(f"Значения не образуют однозначную сетку X × Y ({dup} повторов): уточните фильтр.")
            return
        finite = grid[np.isfinite(grid)]
        if finite.size == 0:
            self.info.setText("Нет значений, полученных от ядра, для выбранной величины цвета.")
            return
        # ячейки строятся вокруг узлов сетки (границы — посередине между узлами, в том числе
        # для неравномерной сетки); значения в ячейках — ровно значения ядра в узлах
        log_x, log_y = self.log_x.isChecked(), self.log_y.isChecked()
        ex, ey = _edges(xs, log_x), _edges(yv, log_y)
        X, Y = np.meshgrid(ex, ey, indexing="ij")
        cmap = pg.colormap.get("viridis")
        self.image = pg.PColorMeshItem(X, Y, grid, colorMap=cmap)
        self.plot.addItem(self.image)
        self.plot.setLabel("bottom", xc.label)
        self.plot.setLabel("left", yc.label)
        self.plot.setLogMode(x=False, y=False)
        self.colorbar = pg.ColorBarItem(values=(float(finite.min()), float(finite.max())), colorMap=cmap,
                                        label=zc.label, interactive=False)
        self.colorbar.setImageItem(self.image, insert_in=self.plot)
        self.plot.enableAutoRange()
        n_nan = int(np.sum(~np.isfinite(grid)))
        text = (f"Сетка {len(xs)} × {len(yv)}; {zc.label}: {fmt(float(finite.min()))} … {fmt(float(finite.max()))}.")
        if n_nan:
            text += f" Узлов без результата ядра: {n_nan} — оставлены пустыми."
        self.info.setText(text)
        self._map = (xs, yv, grid)

    def _mouse(self, evt) -> None:
        pos = evt[0]
        if not self.plot.sceneBoundingRect().contains(pos):
            return
        p = self.plot.vb.mapSceneToView(pos)
        x, y = p.x(), p.y()
        if self.log_x.isChecked() and self.mode.currentData() == "lines":
            x = 10 ** x
        if self.log_y.isChecked() and self.mode.currentData() == "lines":
            y = 10 ** y
        self.cursor.setText(f"X = {fmt(x, 5)}, Y = {fmt(y, 5)}")

    # ------------------------------------------------------------ тема и экспорт
    def apply_theme(self, name: str) -> None:
        self._theme = name if name in THEMES else "dark"
        bg, fg = THEMES[self._theme]
        self.glw.setBackground(bg)
        for ax in ("bottom", "left"):
            a = self.plot.getAxis(ax)
            a.setPen(fg)
            a.setTextPen(fg)
        self.legend.setLabelTextColor(fg)

    def save(self, path: str | Path) -> Path:
        from pyqtgraph.exporters import ImageExporter
        path = Path(path)
        target = self.glw.scene()
        if path.suffix.lower() == ".svg":
            # векторный вывод через QSvgGenerator: SVG-экспортёр PyQtGraph не разбирает вывод Qt 6
            from PySide6.QtCore import QRectF, QSize
            from PySide6.QtGui import QPainter
            from PySide6.QtSvg import QSvgGenerator
            rect = self.glw.mapToScene(self.glw.viewport().rect()).boundingRect()
            gen = QSvgGenerator()
            gen.setFileName(str(path))
            gen.setSize(QSize(int(rect.width()), int(rect.height())))
            gen.setViewBox(QRectF(0, 0, rect.width(), rect.height()))
            gen.setTitle("График Astra")
            gen.setDescription("Построено по результатам ядра NASA CEA")
            painter = QPainter(gen)
            try:
                painter.fillRect(QRectF(0, 0, rect.width(), rect.height()), pg.mkColor(THEMES[self._theme][0]))
                target.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
            finally:
                painter.end()
        else:
            exp = ImageExporter(target)
            exp.parameters()["width"] = max(1600, int(self.glw.width() * 2))
            exp.export(str(path))
        return path

    def plot_image(self, path: str | Path) -> bool:
        """PNG текущего графика для отчёта; False, если строить нечего."""
        if not self.data or not self.plot.listDataItems() and self.image is None:
            return False
        self.save(path)
        return Path(path).exists()

    def save_dialog(self, kind: str) -> None:
        filt = "Изображение PNG (*.png)" if kind == "png" else "Векторное изображение SVG (*.svg)"
        name, _ = QFileDialog.getSaveFileName(self, "Сохранить график", f"график.{kind}", filt)
        if name:
            if not name.lower().endswith(f".{kind}"):
                name += f".{kind}"
            self.save(name)
            self.state.message.emit(f"График сохранён: {name}")
