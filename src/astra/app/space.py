"""Рисованные элементы космического оформления: звёздный фон, значки разделов, значок программы,
маршрут расчёта и схема двигателя с параметрами по сечениям.

Здесь нет ни одной расчётной формулы: схема двигателя только показывает значения, полученные
от ядра NASA CEA, а её контур условный (не в масштабе).
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .theme import MONO_FAMILIES, colors

UI_FAMILIES = ["Segoe UI", "Inter", "Noto Sans"]


def _font(px: int, bold: bool = False, mono: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont()
    f.setFamilies(MONO_FAMILIES if mono else UI_FAMILIES)
    f.setPixelSize(px)
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def _alpha(color: str, a: int) -> QColor:
    q = QColor(color)
    q.setAlpha(a)
    return q


# ------------------------------------------------------------------ фон
class SpaceBackground(QWidget):
    """Градиент глубокого космоса, туманности, звёзды и линии орбит. Рисуется один раз на размер окна."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpaceBackground")
        self._theme = "dark"
        self._cache: QPixmap | None = None
        rnd = random.Random(7)
        self._stars = [(rnd.random(), rnd.random(), rnd.random()) for _ in range(300)]

    def set_theme(self, name: str) -> None:
        self._theme = name
        self._cache = None
        self.update()

    def resizeEvent(self, e) -> None:
        self._cache = None
        super().resizeEvent(e)

    def _render(self) -> QPixmap:
        c = colors(self._theme)
        dpr = self.devicePixelRatioF()
        W, H = max(1, self.width()), max(1, self.height())
        pm = QPixmap(int(W * dpr), int(H * dpr))
        pm.setDevicePixelRatio(dpr)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, W * 0.3, H)
        g.setColorAt(0, QColor(c["bg"]))
        g.setColorAt(1, QColor(c["bg2"]))
        p.fillRect(QRectF(0, 0, W, H), g)
        for cx, cy, r, col, a in ((0.85, 0.10, 0.45, c["neb1"], 70), (0.08, 0.92, 0.50, c["neb2"], 45),
                                  (0.55, 0.55, 0.35, c["neb1"], 22)):
            rg = QRadialGradient(QPointF(W * cx, H * cy), W * r)
            rg.setColorAt(0, _alpha(col, a))
            rg.setColorAt(1, _alpha(col, 0))
            p.fillRect(QRectF(0, 0, W, H), rg)
        p.setPen(Qt.PenStyle.NoPen)
        lo, hi = c["star_alpha"]
        for x, y, s in self._stars[: c["stars"]]:
            q = QColor(c["star"])
            q.setAlphaF(lo + (hi - lo) * s * s)
            p.setBrush(q)
            rr = 0.5 + 1.3 * s ** 3
            p.drawEllipse(QPointF(x * W, y * H), rr, rr)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_alpha(c["accent"], 26), 1))
        p.drawEllipse(QPointF(W * 0.95, -H * 0.1), W * 0.42, H * 0.38)
        p.drawEllipse(QPointF(W * 0.95, -H * 0.1), W * 0.55, H * 0.52)
        p.end()
        return pm

    def paintEvent(self, e) -> None:
        if self._cache is None or self._cache.size() != self.size() * self.devicePixelRatioF():
            self._cache = self._render()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        p.end()


# ------------------------------------------------------------------ значки разделов
def _icon_path(key: str, s: float) -> list[tuple[QPainterPath, bool]]:
    """Контуры значка в квадрате s×s: (контур, заливка)."""
    out: list[tuple[QPainterPath, bool]] = []
    P = QPainterPath
    if key == "home":
        a = P(QPointF(s * .15, s * .5)); a.lineTo(s * .5, s * .18); a.lineTo(s * .85, s * .5)
        b = P(); b.addRect(QRectF(s * .27, s * .47, s * .46, s * .37))
        out += [(a, False), (b, False)]
    elif key == "propellant":          # капля
        a = P(QPointF(s * .5, s * .12))
        a.cubicTo(s * .5, s * .12, s * .2, s * .5, s * .2, s * .63)
        a.arcTo(QRectF(s * .2, s * .33, s * .6, s * .55), 180, 180)
        a.cubicTo(s * .8, s * .5, s * .5, s * .12, s * .5, s * .12)
        out.append((a, False))
    elif key == "conditions":          # ползунки
        for i, x in enumerate((.3, .6, .45)):
            y = s * (.27 + .23 * i)
            a = P(QPointF(s * .14, y)); a.lineTo(s * .86, y)
            out.append((a, False))
            b = P(); b.addEllipse(QPointF(s * x, y), s * .07, s * .07)
            out.append((b, True))
    elif key == "thermo":              # пламя
        a = P(QPointF(s * .5, s * .1))
        a.cubicTo(s * .78, s * .38, s * .82, s * .62, s * .68, s * .78)
        a.arcTo(QRectF(s * .28, s * .5, s * .44, s * .38), 0, -180)
        a.cubicTo(s * .2, s * .55, s * .35, s * .45, s * .5, s * .1)
        out.append((a, False))
        b = P(); b.addEllipse(QPointF(s * .5, s * .7), s * .08, s * .08)
        out.append((b, True))
    elif key == "parametric":          # семейство кривых
        for k in range(3):
            a = P(QPointF(s * .14, s * (.8 - .12 * k)))
            a.cubicTo(s * .4, s * (.8 - .12 * k), s * .5, s * (.3 - .05 * k), s * .86, s * (.35 - .08 * k))
            out.append((a, False))
    elif key == "nozzle":              # сопло
        for sg in (-1, 1):
            a = P(QPointF(s * .12, s * (.5 + sg * .14)))
            a.lineTo(s * .32, s * (.5 + sg * .14))
            a.cubicTo(s * .42, s * (.5 + sg * .14), s * .42, s * (.5 + sg * .06), s * .5, s * (.5 + sg * .06))
            a.cubicTo(s * .65, s * (.5 + sg * .08), s * .78, s * (.5 + sg * .26), s * .88, s * (.5 + sg * .34))
            out.append((a, False))
    elif key == "isp":                 # стрелка-ракета вверх
        a = P(QPointF(s * .5, s * .1)); a.lineTo(s * .7, s * .4); a.lineTo(s * .58, s * .4)
        a.lineTo(s * .58, s * .72); a.lineTo(s * .42, s * .72); a.lineTo(s * .42, s * .4); a.lineTo(s * .3, s * .4)
        a.closeSubpath()
        b = P(QPointF(s * .42, s * .82)); b.lineTo(s * .42, s * .9)
        c = P(QPointF(s * .58, s * .82)); c.lineTo(s * .58, s * .9)
        out += [(a, False), (b, False), (c, False)]
    elif key == "plots":
        a = P(QPointF(s * .14, s * .14)); a.lineTo(s * .14, s * .86); a.lineTo(s * .86, s * .86)
        b = P(QPointF(s * .22, s * .72)); b.lineTo(s * .42, s * .48); b.lineTo(s * .58, s * .6); b.lineTo(s * .82, s * .26)
        out += [(a, False), (b, False)]
    elif key == "tables":
        a = P(); a.addRoundedRect(QRectF(s * .14, s * .2, s * .72, s * .6), s * .08, s * .08)
        out.append((a, False))
        for y in (.4, .6):
            b = P(QPointF(s * .14, s * y)); b.lineTo(s * .86, s * y); out.append((b, False))
        c = P(QPointF(s * .4, s * .2)); c.lineTo(s * .4, s * .8); out.append((c, False))
    elif key == "database":            # цилиндр
        a = P(); a.addEllipse(QRectF(s * .2, s * .14, s * .6, s * .2)); out.append((a, False))
        b = P(QPointF(s * .2, s * .24)); b.lineTo(s * .2, s * .76)
        b.arcTo(QRectF(s * .2, s * .66, s * .6, s * .2), 180, 180); b.lineTo(s * .8, s * .24)
        out.append((b, False))
        c = P(QPointF(s * .2, s * .5)); c.arcTo(QRectF(s * .2, s * .4, s * .6, s * .2), 180, 180)
        out.append((c, False))
    elif key == "projects":            # папка
        a = P(QPointF(s * .12, s * .28)); a.lineTo(s * .4, s * .28); a.lineTo(s * .48, s * .36)
        a.lineTo(s * .88, s * .36); a.lineTo(s * .88, s * .8); a.lineTo(s * .12, s * .8); a.closeSubpath()
        out.append((a, False))
    elif key == "settings":            # шестерня
        a = P(); a.addEllipse(QPointF(s * .5, s * .5), s * .14, s * .14); out.append((a, False))
        for k in range(8):
            ang = k * math.pi / 4
            b = P(QPointF(s * .5 + math.cos(ang) * s * .24, s * .5 + math.sin(ang) * s * .24))
            b.lineTo(s * .5 + math.cos(ang) * s * .36, s * .5 + math.sin(ang) * s * .36)
            out.append((b, False))
        c = P(); c.addEllipse(QPointF(s * .5, s * .5), s * .26, s * .26); out.append((c, False))
    return out


def section_icon(key: str, color: str, size: int = 18) -> QIcon:
    icon = QIcon()
    for dpr in (1, 2):
        pm = QPixmap(size * dpr, size * dpr)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), max(1.3, size / 12))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        for path, fill in _icon_path(key, size):
            p.setPen(pen)
            p.setBrush(QColor(color) if fill else Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.end()
        icon.addPixmap(pm)
    return icon


def app_icon_pixmap(size: int = 256) -> QPixmap:
    """Значок программы: тёмный круг-космос, орбита, раскалённая планета и спутник."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    bg = QRadialGradient(QPointF(s * .35, s * .3), s * .8)
    bg.setColorAt(0, QColor("#2a2370"))
    bg.setColorAt(.55, QColor("#0d1240"))
    bg.setColorAt(1, QColor("#04050d"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(QRectF(s * .04, s * .04, s * .92, s * .92), s * .22, s * .22)
    rnd = random.Random(3)
    for _ in range(26):
        x, y, r = rnd.uniform(.12, .88), rnd.uniform(.12, .88), rnd.random()
        p.setBrush(_alpha("#ffffff", int(60 + 150 * r)))
        p.drawEllipse(QPointF(s * x, s * y), s * (.004 + .008 * r), s * (.004 + .008 * r))
    c = QPointF(s * .5, s * .52)
    glow = QRadialGradient(c, s * .32)
    glow.setColorAt(0, _alpha("#ffb547", 140))
    glow.setColorAt(1, _alpha("#ffb547", 0))
    p.setBrush(glow)
    p.drawEllipse(c, s * .32, s * .32)
    orbit = QRectF(-s * .36, -s * .13, s * .72, s * .26)
    pen = QPen(QColor("#5ee7ff"), s * .028)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)

    def ring(start: int) -> None:      # половина орбиты: задняя (за планетой) или передняя
        p.save()
        p.translate(c)
        p.rotate(-22)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        p.drawArc(orbit, start * 16, 180 * 16)
        p.restore()

    ring(0)
    planet = QRadialGradient(QPointF(s * .44, s * .44), s * .22)
    planet.setColorAt(0, QColor("#fff3d6"))
    planet.setColorAt(.35, QColor("#ffb547"))
    planet.setColorAt(1, QColor("#d9481a"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(planet)
    p.drawEllipse(c, s * .17, s * .17)
    ring(180)
    p.save()
    p.translate(c)
    p.rotate(-22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(s * .33, s * .05), s * .035, s * .035)
    p.restore()
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_icon_pixmap(sz))
    return icon


# ------------------------------------------------------------------ маршрут расчёта
class RouteBar(QWidget):
    """Шаги работы с проектом в виде траектории полёта. Щелчок по шагу открывает раздел.

    steps: список словарей {key, title, sub, done}; current — ключ открытого раздела.
    """

    step_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RouteBar")
        self._theme = "dark"
        self.steps: list[dict] = []
        self.current = ""
        self._rects: list[tuple[QRectF, str]] = []
        self.setFixedHeight(84)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_theme(self, name: str) -> None:
        self._theme = name
        self.update()

    def set_steps(self, steps: list[dict], current: str) -> None:
        self.steps, self.current = steps, current
        self.setToolTip("")
        self.update()

    def mouseMoveEvent(self, e) -> None:
        hit = next((k for r, k in self._rects if r.contains(e.position())), None)
        self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
        step = next((s for s in self.steps if s["key"] == hit), None)
        self.setToolTip(step.get("tip", "") if step else "")

    def mousePressEvent(self, e) -> None:
        for r, key in self._rects:
            if r.contains(e.position()):
                self.step_clicked.emit(key)
                return

    def paintEvent(self, e) -> None:
        if not self.steps:
            return
        c = colors(self._theme)
        dark = self._theme == "dark"
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self.steps)
        W = self.width()
        gap, y, h = 22.0, 10.0, 60.0
        bw = (W - gap * (n - 1)) / n
        mid = y + h / 2
        p.setPen(QPen(_alpha(c["accent"], 110), 1.5, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(4, mid), QPointF(W - 4, mid))
        last_done = max((i for i, s in enumerate(self.steps) if s["done"]), default=-1)
        if last_done >= 0:
            p.setPen(QPen(QColor(c["accent"]), 2.5))
            p.drawLine(QPointF(4, mid), QPointF(last_done * (bw + gap) + bw, mid))
        self._rects = []
        for i, s in enumerate(self.steps):
            x = i * (bw + gap)
            rect = QRectF(x, y, bw, h)
            self._rects.append((rect, s["key"]))
            now = s["key"] == self.current
            if now:
                p.setPen(Qt.PenStyle.NoPen)
                for k in range(6, 0, -1):
                    p.setBrush(_alpha(c["accent"], 10))
                    p.drawRoundedRect(rect.adjusted(-k * 2, -k * 2, k * 2, k * 2), 16 + k, 16 + k)
            fill = QColor(c["panel"])
            fill.setAlpha(235)
            p.setBrush(fill)
            edge = QColor(c["accent"]) if (s["done"] or now) else QColor(c["border"])
            p.setPen(QPen(edge, 1.6 if now else 1.1))
            p.drawRoundedRect(rect, 15, 15)
            cxy = QPointF(x + 25, mid)
            if now:
                rg = QRadialGradient(cxy, 12)
                rg.setColorAt(0, QColor("#ffffff"))
                rg.setColorAt(.45, QColor(c["accent2"]))
                rg.setColorAt(1, QColor(c["accent2"]).darker(140))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(rg)
                p.drawEllipse(cxy, 10, 10)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(c["accent2"]), 1))
                p.drawEllipse(cxy, 16, 6.5)
            elif s["done"]:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(c["accent"]))
                p.drawEllipse(cxy, 10, 10)
                pen = QPen(QColor(c["accent_text"] if dark else "#ffffff"), 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawPolyline([QPointF(x + 20, mid), QPointF(x + 24, mid + 4), QPointF(x + 31, mid - 4)])
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(c["muted"]), 1.4))
                p.drawEllipse(cxy, 9.5, 9.5)
                p.setFont(_font(11, mono=True))
                p.drawText(QRectF(x + 15, mid - 10, 20, 20), Qt.AlignmentFlag.AlignCenter, str(i + 1))
            tx = x + 46
            tw = bw - 52
            p.setFont(_font(13, bold=True))
            p.setPen(QColor(c["text"] if (s["done"] or now) else c["muted"]))
            p.drawText(QRectF(tx, y + 9, tw, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(s["title"], Qt.TextElideMode.ElideRight, int(tw)))
            p.setFont(_font(11, mono=True))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(tx, y + 31, tw, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(s["sub"], Qt.TextElideMode.ElideRight, int(tw)))
        p.end()


# ------------------------------------------------------------------ схема двигателя
class EngineDiagram(QWidget):
    """Условный контур камеры и сопла; над сечениями — значения из результата ядра.

    stations: три словаря {title, rows: [(обозначение, значение, единица)]} — камера, критика, срез;
    headline: (подпись, значение, пояснение) — крупное число справа.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EngineDiagram")
        self._theme = "dark"
        self.stations: list[dict] = []
        self.headline: tuple[str, str, str] = ("", "—", "")
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_theme(self, name: str) -> None:
        self._theme = name
        self.update()

    def set_data(self, stations: list[dict], headline: tuple[str, str, str]) -> None:
        self.stations, self.headline = stations, headline
        self.update()

    def paintEvent(self, e) -> None:
        c = colors(self._theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = float(self.width()), float(self.height())
        p.setPen(QPen(_alpha(c["accent"], 50), 1))
        p.setBrush(_alpha(c["panel"], 170))
        p.drawRoundedRect(QRectF(.5, .5, W - 1, H - 1), 16, 16)

        cy = H * .66
        x0, x1, xt, x3 = 28.0, W * .20, W * .33, W * .62
        Rc, Rt, Re = H * .14, H * .055, H * .27

        def wall(sg: int) -> QPainterPath:
            pa = QPainterPath(QPointF(x0, cy + sg * Rc))
            pa.lineTo(x1, cy + sg * Rc)
            pa.cubicTo(x1 + (xt - x1) * .55, cy + sg * Rc, xt - (xt - x1) * .35, cy + sg * Rt, xt, cy + sg * Rt)
            pa.cubicTo(xt + (x3 - xt) * .25, cy + sg * Rt, x3 - (x3 - xt) * .45, cy + sg * Re * .92, x3, cy + sg * Re)
            return pa

        up, lo = wall(-1), wall(1)
        body = QPainterPath(up)
        body.lineTo(x3, cy + Re)
        body.connectPath(lo.toReversed())
        body.closeSubpath()

        # факел за срезом сопла (декоративный)
        xe = W * .97
        plume = QPainterPath(QPointF(x3, cy - Re * .96))
        plume.cubicTo(x3 + (xe - x3) * .3, cy - Re * .75, x3 + (xe - x3) * .7, cy - Re * .35, xe, cy - Re * .08)
        plume.lineTo(xe, cy + Re * .08)
        plume.cubicTo(x3 + (xe - x3) * .7, cy + Re * .35, x3 + (xe - x3) * .3, cy + Re * .75, x3, cy + Re * .96)
        plume.closeSubpath()
        pg = QLinearGradient(x3, 0, xe, 0)
        for t, col, a in ((0, c["plume"][0], 210), (.35, c["plume"][1], 140), (1, c["plume"][2], 0)):
            pg.setColorAt(t, _alpha(col, a))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(plume, pg)
        for k in range(4):
            xa = x3 + (xe - x3) * (.08 + .2 * k)
            L, hh = (xe - x3) * .18, Re * (.42 - .08 * k)
            dm = QPainterPath(QPointF(xa, cy))
            dm.lineTo(xa + L / 2, cy - hh)
            dm.lineTo(xa + L, cy)
            dm.lineTo(xa + L / 2, cy + hh)
            dm.closeSubpath()
            p.fillPath(dm, _alpha("#ffffff", int(c["diamond_alpha"] * (1 - .22 * k))))

        g = QLinearGradient(x0, 0, x3, 0)
        for t, col in c["flame"]:
            g.setColorAt(t, QColor(col))
        p.fillPath(body, QBrush(g))
        p.setPen(QPen(QColor(c["contour"]), 2.2))
        p.drawPath(up)
        p.drawPath(lo)
        p.drawLine(QPointF(x0, cy - Rc), QPointF(x0, cy + Rc))
        p.setPen(QPen(_alpha(c["muted"], 120), 1, Qt.PenStyle.DashDotLine))
        p.drawLine(QPointF(14, cy), QPointF(W - 14, cy))

        xs = (x0 + (x1 - x0) * .45, xt, x3)
        for x, st in zip(xs, self.stations):
            p.setPen(QPen(_alpha(c["accent"], 140), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, 22), QPointF(x, H - 16))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["accent"]))
            p.drawEllipse(QPointF(x, cy), 3.5, 3.5)
            p.setFont(_font(10, bold=True, mono=True, spacing=1.5))
            p.setPen(QColor(c["accent"]))
            p.drawText(QPointF(x + 10, 32), st["title"])
            for j, (sym, val, unit) in enumerate(st["rows"]):
                yy = 56 + j * 22
                p.setFont(_font(13))
                p.setPen(QColor(c["muted"]))
                p.drawText(QPointF(x + 10, yy), sym)
                p.setFont(_font(15, bold=True, mono=True))
                p.setPen(QColor(c["text"]))
                p.drawText(QPointF(x + 50, yy), f"{val} {unit}".rstrip())

        cap, big, note = self.headline
        bx = W * .80
        p.setFont(_font(10, bold=True, mono=True, spacing=1.5))
        p.setPen(QColor(c["accent2"]))
        p.drawText(QPointF(bx, 32), cap)
        p.setFont(_font(34, bold=True, mono=True))
        p.setPen(QColor(c["text"]))
        p.drawText(QPointF(bx, 72), big)
        p.setFont(_font(12, mono=True))
        p.setPen(QColor(c["muted"]))
        p.drawText(QPointF(bx, 92), note)
        p.setFont(_font(10))
        p.drawText(QPointF(16, H - 12), "Контур условный, не в масштабе")
        p.end()


# ------------------------------------------------------------------ мелкие изображения для таблицы стилей
def ui_assets(name: str) -> dict[str, str]:
    """Стрелки полей ввода и галочка флажка в цветах темы: PNG во временной папке пользователя.

    Таблица стилей Qt принимает изображения только по пути, поэтому они рисуются при запуске.
    """
    import tempfile
    from pathlib import Path

    c = colors(name)
    folder = Path(tempfile.gettempdir()) / "astra-ui"
    folder.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}

    def draw(fname: str, size: int, painter) -> None:
        pm = QPixmap(size * 2, size * 2)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(2, 2)
        painter(p, size)
        p.end()
        path = folder / f"{name}-{fname}.png"
        pm.save(str(path))
        out[fname] = path.as_posix()

    def chevron(up: bool):
        def f(p: QPainter, s: int) -> None:
            pen = QPen(QColor(c["muted"]), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            y0, y1 = (s * .62, s * .38) if up else (s * .38, s * .62)
            p.drawPolyline([QPointF(s * .28, y0), QPointF(s * .5, y1), QPointF(s * .72, y0)])
        return f

    def check(p: QPainter, s: int) -> None:
        pen = QPen(QColor(c["accent_text"]), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(s * .22, s * .52), QPointF(s * .42, s * .72), QPointF(s * .78, s * .3)])

    draw("down", 12, chevron(False))
    draw("up", 12, chevron(True))
    draw("check", 14, check)
    return out
