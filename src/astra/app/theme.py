"""Единая цветовая система Astra в космическом стиле.

Две темы: «Глубокий космос» (тёмная) и «Орбита днём» (светлая). Цвета задаются здесь и
используются и в таблице стилей Qt, и в рисованных элементах (фон, маршрут, схема двигателя).
"""

from __future__ import annotations

THEMES = {
    "dark": {
        # фон: градиент bg → bg2, туманности neb1/neb2, звёзды star
        "bg": "#04050d", "bg2": "#0a0f2e", "neb1": "#5b2bd6", "neb2": "#0fb5d6", "star": "#ffffff",
        "stars": 260, "star_alpha": (0.25, 1.0),
        "panel": "#0e1538", "panel2": "#18214f", "glass": "rgba(16, 22, 56, 200)", "glass2": "rgba(28, 36, 82, 170)",
        "border": "#283063", "border_soft": "rgba(120, 140, 255, 70)",
        "text": "#e9ecff", "muted": "#8890b8", "input": "rgba(6, 10, 30, 210)",
        "accent": "#5ee7ff", "accent2": "#ffb547", "accent_text": "#05121c",
        "good": "#3ee0a0", "warn": "#ffb547", "bad": "#ff6b7a",
        "sel": "rgba(94, 231, 255, 45)", "alt": "rgba(255, 255, 255, 9)",
        "contour": "#7fdcff",
        "flame": [(0.0, "#ff7a2a"), (0.22, "#d9481a"), (0.4, "#a33bd0"), (0.7, "#3a2c8f"), (1.0, "#14204f")],
        "plume": ["#bff4ff", "#5ee7ff", "#7a5cff"], "diamond_alpha": 55,
        "plot_bg": "#0b1133",
    },
    "light": {
        "bg": "#f4f7ff", "bg2": "#dfe7fb", "neb1": "#b7a6ff", "neb2": "#8fe0f2", "star": "#4a5cc7",
        "stars": 120, "star_alpha": (0.12, 0.37),
        "panel": "#ffffff", "panel2": "#eef2fd", "glass": "rgba(255, 255, 255, 215)", "glass2": "rgba(240, 244, 255, 200)",
        "border": "#c6cff0", "border_soft": "rgba(60, 80, 200, 50)",
        "text": "#0e1640", "muted": "#5a6390", "input": "rgba(255, 255, 255, 235)",
        "accent": "#2f45d8", "accent2": "#ff7a1a", "accent_text": "#ffffff",
        "good": "#12925f", "warn": "#c25e00", "bad": "#d12f45",
        "sel": "rgba(47, 69, 216, 32)", "alt": "rgba(47, 69, 216, 7)",
        "contour": "#2f45d8",
        "flame": [(0.0, "#ffb37a"), (0.22, "#ff8a4a"), (0.4, "#c58cff"), (0.7, "#9fb2ff"), (1.0, "#dbe4ff")],
        "plume": ["#ffffff", "#8fd8ff", "#9a8cff"], "diamond_alpha": 120,
        "plot_bg": "#ffffff",
    },
}

THEME_NAMES = {"dark": "Глубокий космос (тёмная)", "light": "Орбита днём (светлая)"}

# шрифты: Segoe UI и Consolas есть в любой Windows, остальные — для других систем
UI_FONT = "'Segoe UI', 'Inter', 'Noto Sans', sans-serif"
MONO_FONT = "'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', monospace"
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New"]


def colors(name: str) -> dict:
    return THEMES[name if name in THEMES else "dark"]


def stylesheet(name: str, assets: dict[str, str] | None = None) -> str:
    """Таблица стилей Qt; assets — пути к стрелкам и галочке (см. space.ui_assets)."""
    c = colors(name)
    return _base(c) + (_assets(c, assets) if assets else "")


def _assets(c: dict, a: dict[str, str]) -> str:
    return f"""
    QComboBox::down-arrow {{ image: url("{a['down']}"); width: 12px; height: 12px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border; width: 18px; border: none; background: transparent; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{a['up']}"); width: 10px; height: 10px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{a['down']}"); width: 10px; height: 10px; }}
    QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{ image: url("{a['check']}"); }}
    """


def _base(c: dict) -> str:
    return f"""
    QWidget {{ color: {c['text']}; font-family: {UI_FONT}; font-size: 10pt; }}
    QMainWindow, QDialog, QMessageBox, QFileDialog, QInputDialog {{ background: {c['bg2']}; }}
    QDialog QWidget, QMessageBox QWidget {{ background: transparent; }}
    QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['accent']}; padding: 6px;
        border-radius: 6px; }}
    QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
    QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget, #Root, #TopBar, #NavRow {{
        background: transparent; border: none; }}

    /* верхняя строка */
    #LogoMark {{ color: {c['accent2']}; font-size: 17pt; }}
    #Logo {{ font-size: 16pt; font-weight: 800; letter-spacing: 4px; }}
    #ProjectName {{ color: {c['muted']}; font-size: 10pt; padding-left: 18px; }}
    #Nav {{ background: transparent; border: none; outline: none; }}
    #Nav::item {{ color: {c['muted']}; padding: 6px 10px; margin: 0 1px; border-bottom: 2px solid transparent; }}
    #Nav::item:hover {{ color: {c['text']}; }}
    #Nav::item:selected {{ color: {c['text']}; background: transparent; border-bottom: 2px solid {c['accent']}; }}
    QPushButton#TopButton {{ border-radius: 16px; padding: 6px 14px; }}

    /* страницы */
    #PageTitle {{ font-size: 19pt; font-weight: 800; }}
    #PageHint, #Muted {{ color: {c['muted']}; }}
    #Card {{ background: {c['glass']}; border: 1px solid {c['border_soft']}; border-radius: 14px; }}
    #Card QLabel {{ background: transparent; }}
    #CardTitle {{ font-weight: 700; }}
    #Metric {{ font-family: {MONO_FONT}; font-size: 17pt; font-weight: 700; }}
    #Good {{ color: {c['good']}; }}
    #Warn {{ color: {c['warn']}; }}
    #Bad {{ color: {c['bad']}; }}

    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 4px 8px; min-height: 18px;
        selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; }}
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {c['accent']}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {c['bad']}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{ background: {c['panel']}; border: 1px solid {c['border']};
        selection-background-color: {c['sel']}; selection-color: {c['text']}; outline: none; }}
    QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {c['sel']}; }}

    QPushButton {{ background: {c['glass']}; border: 1px solid {c['border']}; border-radius: 15px; padding: 6px 16px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:pressed {{ background: {c['sel']}; }}
    QPushButton:disabled {{ color: {c['muted']}; border-color: {c['border']}; }}
    QPushButton#Primary {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['accent']}, stop:1 {c['accent2']});
        color: {c['accent_text']}; border: none; font-weight: 700; padding: 7px 20px; }}
    QPushButton#Primary:disabled {{ background: {c['border']}; color: {c['muted']}; }}

    QTableWidget, QTableView, QListWidget, QTreeView {{ background: {c['glass']}; alternate-background-color: {c['alt']};
        gridline-color: {c['border']}; border: 1px solid {c['border_soft']}; border-radius: 12px;
        selection-background-color: {c['sel']}; selection-color: {c['text']}; }}
    QTableWidget, QTableView {{ font-family: {MONO_FONT}; font-size: 9pt; }}
    QTableCornerButton::section {{ background: transparent; border: none; }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{ background: {c['glass2']}; color: {c['muted']}; border: none;
        border-bottom: 1px solid {c['accent']}; padding: 6px 8px; font-family: {UI_FONT}; font-weight: 700; }}

    QTabWidget::pane {{ border: none; background: transparent; top: 2px; }}
    QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 6px 16px; border-radius: 14px;
        margin-right: 4px; border: 1px solid transparent; }}
    QTabBar::tab:selected {{ background: {c['glass']}; color: {c['text']}; border: 1px solid {c['accent']}; }}
    QTabBar::tab:hover {{ color: {c['text']}; }}

    QGroupBox {{ background: {c['glass']}; border: 1px solid {c['border_soft']}; border-radius: 14px;
        margin-top: 16px; padding: 12px 12px 10px 12px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {c['accent']};
        font-family: {MONO_FONT}; font-size: 9pt; letter-spacing: 1px; }}
    QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ background: transparent; }}

    QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {c['muted']};
        background: {c['input']}; }}
    QCheckBox::indicator {{ border-radius: 4px; }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QAbstractItemView::indicator:unchecked {{ border: 1px solid {c['muted']}; background: {c['input']}; border-radius: 4px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked, QAbstractItemView::indicator:checked {{
        background: {c['accent']}; border: 1px solid {c['accent']}; border-radius: 4px; }}
    QRadioButton::indicator:checked {{ border-radius: 8px; }}

    QProgressBar {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 7px; text-align: center;
        height: 14px; }}
    QProgressBar::chunk {{ border-radius: 6px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:1 {c['accent2']}); }}

    QStatusBar {{ background: transparent; color: {c['muted']}; font-family: {MONO_FONT}; font-size: 8pt; }}
    QStatusBar::item {{ border: none; }}
    QSplitter::handle {{ background: {c['border']}; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
    QScrollBar::handle {{ background: {c['border']}; border-radius: 4px; min-height: 30px; min-width: 30px; }}
    QScrollBar::handle:hover {{ background: {c['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """
