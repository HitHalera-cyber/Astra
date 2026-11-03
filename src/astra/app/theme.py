"""Единая цветовая система: графитовая тёмная и светлая темы."""

from __future__ import annotations

THEMES = {
    "dark": {
        "bg": "#1b1e23", "panel": "#23272e", "panel2": "#2b3038", "border": "#363c45",
        "text": "#e4e7eb", "muted": "#98a1ac", "accent": "#4c8dff", "accent_text": "#ffffff",
        "good": "#3fb27f", "warn": "#e0a43a", "bad": "#e5534b", "sel": "#2f4b78", "input": "#1f2328",
    },
    "light": {
        "bg": "#eef0f3", "panel": "#ffffff", "panel2": "#f5f6f8", "border": "#d5d9df",
        "text": "#1c2127", "muted": "#5f6873", "accent": "#2a64d6", "accent_text": "#ffffff",
        "good": "#1d8a5a", "warn": "#a86d00", "bad": "#c3332b", "sel": "#d4e2fb", "input": "#ffffff",
    },
}

THEME_NAMES = {"dark": "Тёмная (графит)", "light": "Светлая"}


def stylesheet(name: str) -> str:
    c = THEMES[name]
    return f"""
    QWidget {{ background: {c['bg']}; color: {c['text']}; font-size: 10pt; }}
    QToolTip {{ background: {c['panel2']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
    #Sidebar {{ background: {c['panel']}; border-right: 1px solid {c['border']}; }}
    #Sidebar QListWidget {{ background: transparent; border: none; outline: none; }}
    #Sidebar QListWidget::item {{ padding: 9px 14px; border-radius: 6px; margin: 1px 8px; color: {c['muted']}; }}
    #Sidebar QListWidget::item:hover {{ background: {c['panel2']}; color: {c['text']}; }}
    #Sidebar QListWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
    #AppTitle {{ font-size: 15pt; font-weight: 600; padding: 16px 18px 2px 18px; background: transparent; }}
    #AppSubtitle {{ color: {c['muted']}; padding: 0 18px 12px 18px; background: transparent; }}
    #PageTitle {{ font-size: 15pt; font-weight: 600; background: transparent; }}
    #PageHint, #Muted {{ color: {c['muted']}; background: transparent; }}
    #Card {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px; }}
    #Card QLabel {{ background: transparent; }}
    #CardTitle {{ font-weight: 600; }}
    #Metric {{ font-size: 16pt; font-weight: 600; }}
    #Good {{ color: {c['good']}; background: transparent; }}
    #Warn {{ color: {c['warn']}; background: transparent; }}
    #Bad {{ color: {c['bad']}; background: transparent; }}
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit {{
        background: {c['input']}; border: 1px solid {c['border']}; border-radius: 5px; padding: 4px 6px;
        selection-background-color: {c['sel']}; }}
    QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {c['bad']}; }}
    QPushButton {{ background: {c['panel2']}; border: 1px solid {c['border']}; border-radius: 5px; padding: 6px 14px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton#Primary {{ background: {c['accent']}; color: {c['accent_text']}; border: none; font-weight: 600; }}
    QTableWidget, QTableView {{ background: {c['panel']}; alternate-background-color: {c['panel2']};
        gridline-color: {c['border']}; border: 1px solid {c['border']}; border-radius: 6px;
        selection-background-color: {c['sel']}; selection-color: {c['text']}; }}
    QHeaderView::section {{ background: {c['panel2']}; color: {c['muted']}; border: none;
        border-bottom: 1px solid {c['border']}; padding: 5px 6px; font-weight: 600; }}
    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 6px; top: -1px; }}
    QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 7px 14px; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; }}
    QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 14px; padding: 10px 10px 8px 10px;
        background: {c['panel']}; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {c['muted']}; font-weight: 600; }}
    QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ background: transparent; }}
    QStatusBar {{ background: {c['panel']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
    QScrollArea {{ border: none; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {c['muted']};
        background: {c['input']}; }}
    QCheckBox::indicator {{ border-radius: 3px; }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QSplitter::handle {{ background: {c['border']}; }}
    """
