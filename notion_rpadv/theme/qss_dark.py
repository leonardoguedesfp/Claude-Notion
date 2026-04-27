"""QSS stylesheet — dark theme.

Usage::

    from notion_rpadv.theme.tokens import DARK
    from notion_rpadv.theme.qss_dark import build_qss
    app.setStyleSheet(build_qss(DARK))

Button variants are selected via a Qt dynamic property:

    btn.setProperty("class", "btn-primary")
    btn.style().unpolish(btn)
    btn.style().polish(btn)

This module mirrors qss_light.py exactly in structure but uses DARK palette
values.  Both modules share the same ``build_qss(palette)`` signature so the
theme manager can call either uniformly.
"""
from __future__ import annotations

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FS_MD,
    FS_LG,
    FS_SM,
    FS_XS,
    RADIUS_MD,
    RADIUS_LG,
    RADIUS_XL,
    RADIUS_SM,
    SP_1,
    SP_2,
    SP_3,
    SP_4,
    SP_5,
    SP_6,
    Palette,
)


def build_qss(p: Palette) -> str:
    """Return a complete QSS stylesheet string for the given Palette.

    The palette is expected to be DARK; for LIGHT call qss_light.build_qss.
    """
    return f"""
/* =========================================================
   RPADV Design System — Dark Theme
   Generated from tokens.py / qss_dark.py
   ========================================================= */

/* ---------------------------------------------------------
   Global reset
   --------------------------------------------------------- */
* {{
    font-family: "{FONT_BODY}", "Segoe UI", "Avenir Next", Arial, sans-serif;
    font-size: {FS_MD}px;
    color: {p.app_fg};
    outline: none;
}}

/* ---------------------------------------------------------
   Application root
   --------------------------------------------------------- */
QMainWindow,
QDialog,
QWidget {{
    background-color: {p.app_bg};
    color: {p.app_fg};
}}

/* Stack / container panels */
QFrame#panel,
QWidget#panel {{
    background-color: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
}}

QFrame#elevated,
QWidget#elevated {{
    background-color: {p.app_elevated};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_XL}px;
}}

/* ---------------------------------------------------------
   Sidebar  (QFrame with objectName="sidebar")
   --------------------------------------------------------- */
QFrame#sidebar {{
    background-color: {p.app_sidebar};
    border: none;
    border-right: 1px solid rgba(255,255,255,0.06);
}}

QLabel#sidebarSection {{
    background: transparent;
    color: {p.app_sidebar_fg_muted};
    font-size: {FS_XS}px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: {SP_3}px {SP_4}px {SP_1}px {SP_4}px;
}}

QFrame#sidebar QLabel {{
    background: transparent;
    color: {p.app_sidebar_fg};
}}

QPushButton#navItem {{
    background: transparent;
    color: {p.app_sidebar_fg};
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: {SP_2}px {SP_3}px;
    font-size: {FS_MD}px;
    font-weight: 500;
    text-align: left;
}}
QPushButton#navItem:hover {{
    background-color: {p.app_sidebar_hover};
}}
QPushButton#navItem:checked,
QPushButton#navItem[active="true"] {{
    background-color: {p.app_sidebar_active};
    color: {p.app_sidebar_fg};
    font-weight: 700;
}}
QPushButton#navItem:pressed {{
    background-color: {p.app_sidebar_active};
}}

/* ---------------------------------------------------------
   Buttons — base reset
   --------------------------------------------------------- */
QPushButton {{
    background-color: {p.app_panel};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_MD}px;
    padding: {SP_2}px {SP_4}px;
    font-size: {FS_MD}px;
    font-weight: 500;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {p.app_elevated};
    border-color: {p.app_border_strong};
}}
QPushButton:pressed {{
    background-color: {p.app_row_selected};
}}
QPushButton:disabled {{
    color: {p.app_fg_subtle};
    background-color: {p.app_bg};
    border-color: {p.app_border};
}}
QPushButton:focus {{
    border-color: {p.app_accent};
}}

/* -- btn-primary ----------------------------------------- */
QPushButton[class="btn-primary"] {{
    background-color: {p.app_accent};
    color: {p.app_accent_fg};
    border: 1px solid {p.app_accent};
    border-radius: {RADIUS_MD}px;
    font-weight: 600;
}}
QPushButton[class="btn-primary"]:hover {{
    background-color: {p.app_accent_hover};
    border-color: {p.app_accent_hover};
}}
QPushButton[class="btn-primary"]:pressed {{
    background-color: {p.app_accent};
    opacity: 0.85;
}}
QPushButton[class="btn-primary"]:disabled {{
    background-color: {p.app_border};
    border-color: {p.app_border};
    color: {p.app_fg_subtle};
}}

/* -- btn-secondary --------------------------------------- */
QPushButton[class="btn-secondary"] {{
    background-color: transparent;
    color: {p.app_accent};
    border: 1px solid {p.app_accent};
    border-radius: {RADIUS_MD}px;
    font-weight: 500;
}}
QPushButton[class="btn-secondary"]:hover {{
    background-color: {p.app_accent_soft};
    border-color: {p.app_accent_hover};
}}
QPushButton[class="btn-secondary"]:pressed {{
    background-color: {p.app_row_selected};
}}
QPushButton[class="btn-secondary"]:disabled {{
    color: {p.app_fg_subtle};
    border-color: {p.app_border};
}}

/* -- btn-ghost ------------------------------------------- */
QPushButton[class="btn-ghost"] {{
    background-color: transparent;
    color: {p.app_fg_muted};
    border: none;
    font-weight: 400;
}}
QPushButton[class="btn-ghost"]:hover {{
    background-color: {p.app_row_hover};
    color: {p.app_fg};
}}
QPushButton[class="btn-ghost"]:pressed {{
    background-color: {p.app_accent_soft};
}}
QPushButton[class="btn-ghost"]:disabled {{
    color: {p.app_fg_subtle};
}}

/* -- btn-danger ------------------------------------------ */
QPushButton[class="btn-danger"] {{
    background-color: {p.app_danger};
    color: #0F1A24;
    border: 1px solid {p.app_danger};
    border-radius: {RADIUS_MD}px;
    font-weight: 600;
}}
QPushButton[class="btn-danger"]:hover {{
    background-color: #E89090;
    border-color: #E89090;
}}
QPushButton[class="btn-danger"]:pressed {{
    background-color: #C06060;
    border-color: #C06060;
}}
QPushButton[class="btn-danger"]:disabled {{
    background-color: {p.app_border};
    border-color: {p.app_border};
    color: {p.app_fg_subtle};
}}

/* ---------------------------------------------------------
   Input fields — QLineEdit, QTextEdit, QPlainTextEdit
   --------------------------------------------------------- */
QLineEdit,
QTextEdit,
QPlainTextEdit {{
    background-color: {p.app_panel};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_MD}px;
    padding: {SP_2}px {SP_3}px;
    font-size: {FS_MD}px;
    selection-background-color: {p.app_accent_soft};
    selection-color: {p.app_fg};
}}
QLineEdit:hover,
QTextEdit:hover,
QPlainTextEdit:hover {{
    border-color: {p.app_border_strong};
}}
QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus {{
    border: 1.5px solid {p.app_accent};
    background-color: {p.app_elevated};
}}
QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled {{
    background-color: {p.app_bg};
    color: {p.app_fg_subtle};
    border-color: {p.app_border};
}}
QLineEdit[invalid="true"] {{
    border-color: {p.app_danger};
}}

/* ---------------------------------------------------------
   QComboBox
   --------------------------------------------------------- */
QComboBox {{
    background-color: {p.app_panel};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_MD}px;
    padding: {SP_2}px {SP_3}px;
    font-size: {FS_MD}px;
    min-height: 28px;
}}
QComboBox:hover {{
    border-color: {p.app_border_strong};
}}
QComboBox:focus,
QComboBox:on {{
    border: 1.5px solid {p.app_accent};
}}
QComboBox:disabled {{
    background-color: {p.app_bg};
    color: {p.app_fg_subtle};
    border-color: {p.app_border};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 20px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.app_fg_muted};
    margin-right: {SP_2}px;
}}
QComboBox QAbstractItemView {{
    background-color: {p.app_elevated};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_MD}px;
    selection-background-color: {p.app_accent_soft};
    selection-color: {p.app_fg};
    padding: {SP_1}px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: {SP_1}px {SP_2}px;
    border-radius: {RADIUS_MD}px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {p.app_row_hover};
}}

/* ---------------------------------------------------------
   QDateEdit / QSpinBox / QDoubleSpinBox
   --------------------------------------------------------- */
QDateEdit,
QSpinBox,
QDoubleSpinBox {{
    background-color: {p.app_panel};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_MD}px;
    padding: {SP_2}px {SP_3}px;
    font-size: {FS_MD}px;
    min-height: 28px;
}}
QDateEdit:hover,
QSpinBox:hover,
QDoubleSpinBox:hover {{
    border-color: {p.app_border_strong};
}}
QDateEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {{
    border: 1.5px solid {p.app_accent};
}}
QDateEdit:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled {{
    background-color: {p.app_bg};
    color: {p.app_fg_subtle};
    border-color: {p.app_border};
}}
QDateEdit::up-button,
QSpinBox::up-button,
QDoubleSpinBox::up-button,
QDateEdit::down-button,
QSpinBox::down-button,
QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 16px;
}}
QDateEdit::drop-down {{
    border: none;
    background: transparent;
    width: 20px;
}}

/* Calendar popup */
QCalendarWidget {{
    background-color: {p.app_elevated};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
}}
QCalendarWidget QToolButton {{
    background-color: transparent;
    color: {p.app_fg};
    border: none;
    border-radius: {RADIUS_MD}px;
    font-weight: 600;
    padding: {SP_1}px {SP_2}px;
}}
QCalendarWidget QToolButton:hover {{
    background-color: {p.app_row_hover};
}}
QCalendarWidget QAbstractItemView {{
    background-color: {p.app_elevated};
    color: {p.app_fg};
    selection-background-color: {p.app_accent};
    selection-color: {p.app_accent_fg};
    gridline-color: {p.app_divider};
}}

/* ---------------------------------------------------------
   QTableView / QTableWidget
   --------------------------------------------------------- */
QTableView,
QTableWidget {{
    background-color: {p.app_panel};
    alternate-background-color: {p.app_bg};
    color: {p.app_fg};
    gridline-color: {p.app_divider};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    selection-background-color: {p.app_row_selected};
    selection-color: {p.app_fg};
    show-decoration-selected: 1;
}}
QTableView::item,
QTableWidget::item {{
    padding: {SP_2}px {SP_3}px;
    border: none;
    color: {p.app_fg};
}}
QTableView::item:hover,
QTableWidget::item:hover {{
    background-color: {p.app_row_hover};
}}
QTableView::item:selected,
QTableWidget::item:selected {{
    background-color: {p.app_row_selected};
    color: {p.app_fg};
}}
QTableView::item[dirty="true"] {{
    background-color: {p.app_cell_dirty};
    border-bottom: 1.5px solid {p.app_cell_dirty_border};
    border-left: 2px solid {p.app_warning};
}}

/* ---------------------------------------------------------
   QHeaderView (table headers)
   --------------------------------------------------------- */
QHeaderView {{
    background-color: {p.app_bg};
    border: none;
}}
QHeaderView::section {{
    background-color: {p.app_bg};
    color: {p.app_fg_subtle};
    border: none;
    border-bottom: 1px solid {p.app_border};
    border-right: 1px solid {p.app_divider};
    padding: {SP_2}px {SP_3}px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}}
QHeaderView::section:hover {{
    background-color: {p.app_row_hover};
    color: {p.app_fg_muted};
}}
QHeaderView::section:checked {{
    background-color: {p.app_accent_soft};
    color: {p.app_accent};
}}
QHeaderView::section:first {{
    border-top-left-radius: {RADIUS_LG}px;
}}
QHeaderView::section:last {{
    border-right: none;
    border-top-right-radius: {RADIUS_LG}px;
}}
QHeaderView::section:vertical {{
    background-color: {p.app_bg};
    border-bottom: 1px solid {p.app_divider};
    border-right: 1px solid {p.app_border};
    color: {p.app_fg_subtle};
    font-size: {FS_SM}px;
    padding: {SP_1}px {SP_2}px;
    text-transform: none;
    letter-spacing: 0;
}}

/* ---------------------------------------------------------
   QScrollBar
   --------------------------------------------------------- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {p.app_border_strong};
    min-height: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.app_fg_subtle};
}}
QScrollBar::handle:vertical:pressed {{
    background: {p.app_fg_muted};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {p.app_border_strong};
    min-width: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p.app_fg_subtle};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {p.app_fg_muted};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
    background: none;
}}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ---------------------------------------------------------
   QSplitter
   --------------------------------------------------------- */
QSplitter::handle {{
    background: {p.app_border};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}
QSplitter::handle:hover {{
    background: {p.app_accent};
}}

/* ---------------------------------------------------------
   QTabWidget / QTabBar
   --------------------------------------------------------- */
QTabWidget::pane {{
    background-color: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    border-top-left-radius: 0;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {p.app_fg_muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: {SP_2}px {SP_4}px;
    font-size: {FS_MD}px;
    font-weight: 500;
    margin-right: {SP_1}px;
}}
QTabBar::tab:hover {{
    color: {p.app_fg};
    border-bottom-color: {p.app_border_strong};
}}
QTabBar::tab:selected {{
    color: {p.app_accent};
    border-bottom-color: {p.app_accent};
    font-weight: 700;
}}

/* ---------------------------------------------------------
   QToolBar
   --------------------------------------------------------- */
QToolBar {{
    background-color: {p.app_panel};
    border: none;
    border-bottom: 1px solid {p.app_border};
    spacing: {SP_1}px;
    padding: {SP_1}px {SP_2}px;
}}
QToolBar::separator {{
    width: 1px;
    background: {p.app_border};
    margin: {SP_2}px {SP_2}px;
}}
QToolButton {{
    background: transparent;
    color: {p.app_fg_muted};
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: {SP_1}px {SP_2}px;
    font-size: {FS_MD}px;
}}
QToolButton:hover {{
    background-color: {p.app_row_hover};
    color: {p.app_fg};
}}
QToolButton:pressed,
QToolButton:checked {{
    background-color: {p.app_accent_soft};
    color: {p.app_accent};
}}

/* ---------------------------------------------------------
   QMenuBar / QMenu
   --------------------------------------------------------- */
QMenuBar {{
    background-color: {p.app_panel};
    color: {p.app_fg};
    border-bottom: 1px solid {p.app_border};
    padding: {SP_1}px {SP_2}px;
}}
QMenuBar::item {{
    background: transparent;
    padding: {SP_1}px {SP_3}px;
    border-radius: {RADIUS_MD}px;
}}
QMenuBar::item:selected,
QMenuBar::item:pressed {{
    background-color: {p.app_accent_soft};
    color: {p.app_accent};
}}
QMenu {{
    background-color: {p.app_elevated};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    padding: {SP_1}px;
}}
QMenu::item {{
    padding: {SP_2}px {SP_5}px {SP_2}px {SP_3}px;
    border-radius: {RADIUS_MD}px;
    font-size: {FS_MD}px;
}}
QMenu::item:selected {{
    background-color: {p.app_row_hover};
    color: {p.app_fg};
}}
QMenu::item:disabled {{
    color: {p.app_fg_subtle};
}}
QMenu::separator {{
    height: 1px;
    background: {p.app_divider};
    margin: {SP_1}px {SP_2}px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
}}

/* ---------------------------------------------------------
   QStatusBar
   --------------------------------------------------------- */
QStatusBar {{
    background-color: {p.app_panel};
    color: {p.app_fg_muted};
    border-top: 1px solid {p.app_border};
    font-size: {FS_SM}px;
    padding: 0 {SP_3}px;
    min-height: 24px;
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel {{
    color: {p.app_fg_muted};
    font-size: {FS_SM}px;
    background: transparent;
}}

/* ---------------------------------------------------------
   QProgressBar
   --------------------------------------------------------- */
QProgressBar {{
    background-color: {p.app_border};
    border: none;
    border-radius: {RADIUS_SM}px;
    height: 4px;
    text-align: center;
    font-size: {FS_SM}px;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {p.app_accent};
    border-radius: {RADIUS_SM}px;
}}
QProgressBar[variant="success"]::chunk {{
    background-color: {p.app_success};
}}
QProgressBar[variant="warning"]::chunk {{
    background-color: {p.app_warning};
}}
QProgressBar[variant="danger"]::chunk {{
    background-color: {p.app_danger};
}}

/* ---------------------------------------------------------
   QCheckBox / QRadioButton
   --------------------------------------------------------- */
QCheckBox,
QRadioButton {{
    background: transparent;
    color: {p.app_fg};
    font-size: {FS_MD}px;
    spacing: {SP_2}px;
}}
QCheckBox:disabled,
QRadioButton:disabled {{
    color: {p.app_fg_subtle};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {p.app_border_strong};
    border-radius: {RADIUS_SM}px;
    background-color: {p.app_panel};
}}
QCheckBox::indicator:hover {{
    border-color: {p.app_accent};
}}
QCheckBox::indicator:checked {{
    background-color: {p.app_accent};
    border-color: {p.app_accent};
}}
QCheckBox::indicator:disabled {{
    background-color: {p.app_bg};
    border-color: {p.app_border};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {p.app_border_strong};
    border-radius: 8px;
    background-color: {p.app_panel};
}}
QRadioButton::indicator:hover {{
    border-color: {p.app_accent};
}}
QRadioButton::indicator:checked {{
    background-color: {p.app_accent};
    border-color: {p.app_accent};
}}

/* ---------------------------------------------------------
   QLabel variants
   --------------------------------------------------------- */
QLabel {{
    background: transparent;
    color: {p.app_fg};
}}
QLabel[variant="muted"] {{
    color: {p.app_fg_muted};
}}
QLabel[variant="subtle"] {{
    color: {p.app_fg_subtle};
}}
QLabel[variant="accent"] {{
    color: {p.app_accent};
    font-weight: 600;
}}
QLabel[variant="success"] {{
    color: {p.app_success};
}}
QLabel[variant="warning"] {{
    color: {p.app_warning};
}}
QLabel[variant="danger"] {{
    color: {p.app_danger};
}}
QLabel[variant="display"] {{
    font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif;
    font-size: 22px;
    font-weight: 700;
    color: {p.app_fg};
}}
QLabel[variant="heading"] {{
    font-size: {FS_LG}px;
    font-weight: 700;
    color: {p.app_fg};
}}
QLabel[variant="caption"] {{
    font-size: {FS_SM}px;
    color: {p.app_fg_subtle};
}}

/* ---------------------------------------------------------
   QGroupBox
   --------------------------------------------------------- */
QGroupBox {{
    background-color: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    margin-top: 14px;
    padding-top: {SP_3}px;
    font-weight: 600;
    font-size: {FS_MD}px;
    color: {p.app_fg_muted};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {SP_3}px;
    padding: 0 {SP_2}px;
    background-color: {p.app_panel};
    color: {p.app_fg_muted};
    font-size: {FS_SM}px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}

/* ---------------------------------------------------------
   QListWidget / QListView
   --------------------------------------------------------- */
QListWidget,
QListView {{
    background-color: {p.app_panel};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    outline: none;
}}
QListWidget::item,
QListView::item {{
    padding: {SP_2}px {SP_3}px;
    border-radius: {RADIUS_MD}px;
    color: {p.app_fg};
}}
QListWidget::item:hover,
QListView::item:hover {{
    background-color: {p.app_row_hover};
}}
QListWidget::item:selected,
QListView::item:selected {{
    background-color: {p.app_row_selected};
    color: {p.app_fg};
}}

/* ---------------------------------------------------------
   QTreeView / QTreeWidget
   --------------------------------------------------------- */
QTreeView,
QTreeWidget {{
    background-color: {p.app_panel};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    outline: none;
    show-decoration-selected: 1;
}}
QTreeView::item,
QTreeWidget::item {{
    padding: {SP_1}px {SP_2}px;
    border-radius: {RADIUS_MD}px;
    color: {p.app_fg};
}}
QTreeView::item:hover,
QTreeWidget::item:hover {{
    background-color: {p.app_row_hover};
}}
QTreeView::item:selected,
QTreeWidget::item:selected {{
    background-color: {p.app_row_selected};
    color: {p.app_fg};
}}
QTreeView::branch {{
    background: transparent;
}}

/* ---------------------------------------------------------
   Toast / notification overlay  (QFrame#toast)
   --------------------------------------------------------- */
QFrame#toast {{
    background-color: {p.app_elevated};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_XL}px;
    padding: {SP_3}px {SP_4}px;
}}
QFrame#toast[variant="success"] {{
    border-left: 3px solid {p.app_success};
}}
QFrame#toast[variant="warning"] {{
    border-left: 3px solid {p.app_warning};
}}
QFrame#toast[variant="danger"] {{
    border-left: 3px solid {p.app_danger};
}}
QFrame#toast[variant="info"] {{
    border-left: 3px solid {p.app_info};
}}
QFrame#toast QLabel {{
    background: transparent;
    color: {p.app_fg};
}}
QFrame#toast QLabel#toastTitle {{
    font-weight: 700;
    font-size: {FS_MD}px;
}}
QFrame#toast QLabel#toastBody {{
    font-size: {FS_SM}px;
    color: {p.app_fg_muted};
}}

/* ---------------------------------------------------------
   QDialog overrides
   --------------------------------------------------------- */
QDialog {{
    background-color: {p.app_bg};
}}
QDialog QFrame#dialogCard {{
    background-color: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_XL}px;
    padding: {SP_6}px;
}}

/* ---------------------------------------------------------
   QToolTip
   --------------------------------------------------------- */
QToolTip {{
    background-color: {p.app_elevated};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_MD}px;
    padding: {SP_1}px {SP_2}px;
    font-size: {FS_SM}px;
}}

/* ---------------------------------------------------------
   QSlider
   --------------------------------------------------------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: {p.app_border};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {p.app_accent};
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {p.app_accent};
    border-radius: 2px;
}}

/* ---------------------------------------------------------
   Search bar  (QLineEdit#searchBar)
   --------------------------------------------------------- */
QLineEdit#searchBar {{
    background-color: {p.app_elevated};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_XL}px;
    padding: {SP_2}px {SP_4}px;
    font-size: {FS_MD}px;
    color: {p.app_fg};
}}
QLineEdit#searchBar:focus {{
    border: 1.5px solid {p.app_accent};
    background-color: {p.app_panel};
}}

/* ---------------------------------------------------------
   Divider  (QFrame[frameShape="4"] — HLine)
   --------------------------------------------------------- */
QFrame[frameShape="4"] {{
    color: {p.app_divider};
    background: {p.app_divider};
    max-height: 1px;
    border: none;
}}
QFrame[frameShape="5"] {{
    color: {p.app_divider};
    background: {p.app_divider};
    max-width: 1px;
    border: none;
}}
"""
