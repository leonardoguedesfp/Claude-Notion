"""QSS stylesheet — mirrors the HTML prototype's app.css styling.

Usage::

    from notion_rpadv.theme.tokens import LIGHT
    from notion_rpadv.theme.qss_light import build_qss
    app.setStyleSheet(build_qss(LIGHT))

Widget object-name conventions used throughout:

    Sidebar           QWidget#Sidebar
    SidebarItem       QPushButton#SidebarItem          (active="true" property)
    Toolbar           QFrame#Toolbar  / QWidget#Toolbar
    ToolbarTitle      QLabel#ToolbarTitle
    ToolbarMeta       QLabel#ToolbarMeta
    SectionTitle      QLabel#SectionTitle
    KpiValue          QLabel#KpiValue
    Eyebrow           QLabel#Eyebrow
    Card              QFrame#Card
    KpiCard           QFrame#KpiCard                   (alert="true" / warn="true")
    FloatingSaveBar   QFrame#FloatingSaveBar
    Modal             QDialog#Modal
      ModalTitle      QLabel#ModalTitle  (child of Modal)
      ModalEyebrow    QLabel#ModalEyebrow
    BtnPrimary        QPushButton#BtnPrimary
    BtnSecondary      QPushButton#BtnSecondary
    BtnGhost          QPushButton#BtnGhost
    BtnDanger         QPushButton#BtnDanger
    SearchInput       QLineEdit#SearchInput
    Chip              QLabel#Chip
    Chip_blue … _petrol  QLabel#Chip_blue …
"""
from __future__ import annotations

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FONT_DISPLAY,
    FS_SM,
    FS_SM2,
    FS_MD,
    FS_2XL,
    FS_3XL,
    FS_5XL,
    FW_REGULAR,
    FW_MEDIUM,
    FW_SEMIBOLD,
    FW_BOLD,
    SP_1,
    SP_2,
    SP_3,
    SP_4,
    SP_5,
    RADIUS_SM,
    RADIUS_MD,
    RADIUS_LG,
    RADIUS_XL,
    Palette,
)


def build_qss(p: Palette) -> str:
    """Return a complete QSS stylesheet string for the given Palette."""
    return f"""
/* =========================================================
   RPADV Design System — QSS stylesheet
   Mirrors the HTML prototype's app.css styling exactly.
   Generated from tokens.py / qss_light.py
   ========================================================= */

/* ---------------------------------------------------------
   Global reset
   --------------------------------------------------------- */
* {{
    font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
    font-size: {FS_MD}px;
    color: {p.app_fg};
}}

QMainWindow,
QDialog {{
    background: {p.app_bg};
}}

QWidget {{
    background: transparent;
    color: {p.app_fg};
}}

/* ---------------------------------------------------------
   Sidebar  (QWidget#Sidebar)
   --------------------------------------------------------- */
QWidget#Sidebar {{
    background: {p.app_sidebar};
    border: none;
}}

/* ---------------------------------------------------------
   SidebarItem buttons  (QPushButton#SidebarItem)
   --------------------------------------------------------- */
QPushButton#SidebarItem {{
    background: transparent;
    color: {p.app_sidebar_fg};
    font-size: {FS_MD}px;
    font-weight: {FW_MEDIUM};
    text-align: left;
    border: none;
    border-left: 2px solid transparent;
    padding: 7px 16px 7px 14px;
}}
QPushButton#SidebarItem:hover {{
    background: {p.app_sidebar_hover};
}}
QPushButton#SidebarItem[active="true"] {{
    background: {p.app_sidebar_active};
    font-weight: {FW_SEMIBOLD};
    border-left: 2px solid {p.app_sidebar_fg};
}}

/* ---------------------------------------------------------
   Toolbar  (QFrame#Toolbar / QWidget#Toolbar)
   --------------------------------------------------------- */
QFrame#Toolbar,
QWidget#Toolbar {{
    background: {p.app_bg};
    border: none;
    border-bottom: 1px solid {p.app_border};
}}

/* ---------------------------------------------------------
   Toolbar title  (QLabel#ToolbarTitle)
   --------------------------------------------------------- */
QLabel#ToolbarTitle {{
    font-family: "{FONT_DISPLAY}", Georgia, serif;
    font-size: {FS_3XL}px;
    font-weight: {FW_REGULAR};
    color: {p.app_fg_strong};
    background: transparent;
    letter-spacing: -0.2px;
}}

/* ---------------------------------------------------------
   Toolbar meta  (QLabel#ToolbarMeta)
   --------------------------------------------------------- */
QLabel#ToolbarMeta {{
    font-size: {FS_SM}px;
    font-weight: {FW_BOLD};
    letter-spacing: 1.5px;
    color: {p.app_fg_subtle};
    background: transparent;
}}

/* ---------------------------------------------------------
   Section title  (QLabel#SectionTitle)
   --------------------------------------------------------- */
QLabel#SectionTitle {{
    font-family: "{FONT_DISPLAY}", Georgia, serif;
    font-size: {FS_2XL}px;
    font-weight: {FW_REGULAR};
    color: {p.app_fg_strong};
    background: transparent;
}}

/* ---------------------------------------------------------
   KPI value  (QLabel#KpiValue)
   --------------------------------------------------------- */
QLabel#KpiValue {{
    font-family: "{FONT_DISPLAY}", Georgia, serif;
    font-size: {FS_5XL}px;
    font-weight: {FW_REGULAR};
    color: {p.app_fg_strong};
    background: transparent;
    letter-spacing: -0.5px;
}}

/* ---------------------------------------------------------
   Eyebrow labels  (QLabel#Eyebrow)
   --------------------------------------------------------- */
QLabel#Eyebrow {{
    font-size: 10px;
    font-weight: {FW_BOLD};
    letter-spacing: 2px;
    color: {p.app_fg_subtle};
    background: transparent;
}}

/* ---------------------------------------------------------
   Card / panel  (QFrame#Card)
   --------------------------------------------------------- */
QFrame#Card {{
    background: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
}}

/* ---------------------------------------------------------
   KPI card  (QFrame#KpiCard)
   --------------------------------------------------------- */
QFrame#KpiCard {{
    background: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    padding: 14px 16px 16px;
}}
QFrame#KpiCard[alert="true"] QLabel#KpiValue {{
    color: {p.app_danger};
}}
QFrame#KpiCard[warn="true"] QLabel#KpiValue {{
    color: {p.app_warning};
}}

/* ---------------------------------------------------------
   Table  (QTableView)
   --------------------------------------------------------- */
QTableView {{
    background: {p.app_panel};
    border: none;
    gridline-color: {p.app_divider};
    selection-background-color: {p.app_row_selected};
    selection-color: {p.app_fg};
    font-size: {FS_SM2}px;
}}
QTableView::item {{
    padding: 6px 10px;
    border-bottom: 1px solid {p.app_divider};
}}
QTableView::item:hover {{
    background: {p.app_row_hover};
}}
QTableView::item:selected {{
    background: {p.app_row_selected};
}}
QTableView::item[dirty="true"] {{
    background: {p.app_cell_dirty};
    border-bottom: 1px solid {p.app_cell_dirty_border};
}}

/* ---------------------------------------------------------
   Table header  (QHeaderView)
   --------------------------------------------------------- */
QHeaderView {{
    background: {p.app_panel};
    border: none;
}}
QHeaderView::section {{
    background: {p.app_panel};
    font-size: 10px;
    font-weight: {FW_BOLD};
    letter-spacing: 2px;
    color: {p.app_fg_subtle};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {p.app_border_strong};
    text-align: left;
}}
QHeaderView::section:hover {{
    color: {p.app_fg};
}}

/* ---------------------------------------------------------
   Buttons — base reset
   --------------------------------------------------------- */
QPushButton {{
    height: 30px;
    padding: 0 12px;
    border-radius: {RADIUS_MD}px;
    font-size: {FS_SM2}px;
    font-weight: {FW_SEMIBOLD};
    letter-spacing: 0.3px;
    border: 1px solid transparent;
    font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
}}
QPushButton:disabled {{
    opacity: 0.5;
}}

/* Primary — navy fill */
QPushButton#BtnPrimary {{
    background: {p.app_accent};
    color: {p.app_accent_fg};
    border-color: {p.app_accent};
}}
QPushButton#BtnPrimary:hover {{
    background: {p.app_accent_hover};
    border-color: {p.app_accent_hover};
}}

/* Secondary — outline */
QPushButton#BtnSecondary {{
    background: transparent;
    color: {p.app_fg};
    border-color: {p.app_border_strong};
}}
QPushButton#BtnSecondary:hover {{
    background: {p.app_row_hover};
    border-color: {p.app_fg_subtle};
}}

/* Ghost — no border */
QPushButton#BtnGhost {{
    background: transparent;
    color: {p.app_fg_muted};
    border-color: transparent;
}}
QPushButton#BtnGhost:hover {{
    background: {p.app_row_hover};
    color: {p.app_fg};
}}

/* Danger */
QPushButton#BtnDanger {{
    background: {p.app_danger};
    color: white;
    border-color: {p.app_danger};
}}
QPushButton#BtnDanger:hover {{
    background: {p.app_danger};
}}

/* ---------------------------------------------------------
   Input fields  (QLineEdit)
   --------------------------------------------------------- */
QLineEdit {{
    height: 30px;
    padding: 0 10px;
    border-radius: {RADIUS_MD}px;
    border: 1px solid {p.app_border_strong};
    background: {p.app_elevated};
    color: {p.app_fg};
    font-size: {FS_MD}px;
}}
QLineEdit:focus {{
    border-color: {p.app_accent};
}}
QLineEdit#SearchInput {{
    padding-left: 10px;
    min-width: 280px;
}}

/* ---------------------------------------------------------
   ComboBox
   --------------------------------------------------------- */
QComboBox {{
    height: 30px;
    padding: 0 10px;
    border-radius: {RADIUS_MD}px;
    border: 1px solid {p.app_border_strong};
    background: {p.app_elevated};
    color: {p.app_fg};
    font-size: {FS_MD}px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {p.app_elevated};
    border: 1px solid {p.app_border};
}}

/* ---------------------------------------------------------
   Scrollbar
   --------------------------------------------------------- */
QScrollBar:vertical {{
    width: 10px;
    background: transparent;
}}
QScrollBar::handle:vertical {{
    background: {p.app_border_strong};
    border-radius: {RADIUS_MD}px;
    min-height: 20px;
    border: 2px solid transparent;
    background-clip: content-box;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.app_fg_subtle};
    background-clip: content-box;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    height: 10px;
    background: transparent;
}}
QScrollBar::handle:horizontal {{
    background: {p.app_border_strong};
    border-radius: {RADIUS_MD}px;
    min-width: 20px;
    border: 2px solid transparent;
    background-clip: content-box;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p.app_fg_subtle};
    background-clip: content-box;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ---------------------------------------------------------
   Status bar  (QStatusBar)
   --------------------------------------------------------- */
QStatusBar {{
    background: {p.app_sidebar};
    color: {p.app_sidebar_fg_muted};
    font-size: {FS_SM}px;
    border-top: 1px solid rgba(237,234,228,0.08);
}}
QStatusBar::item {{
    border: none;
}}

/* ---------------------------------------------------------
   Chips
   --------------------------------------------------------- */
QLabel#Chip {{
    background: {p.chip_default.bg};
    color: {p.chip_default.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_blue {{
    background: {p.chip_blue.bg};
    color: {p.chip_blue.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_purple {{
    background: {p.chip_purple.bg};
    color: {p.chip_purple.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_green {{
    background: {p.chip_green.bg};
    color: {p.chip_green.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_orange {{
    background: {p.chip_orange.bg};
    color: {p.chip_orange.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_red {{
    background: {p.chip_red.bg};
    color: {p.chip_red.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_yellow {{
    background: {p.chip_yellow.bg};
    color: {p.chip_yellow.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_gray {{
    background: {p.chip_gray.bg};
    color: {p.chip_gray.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_petrol {{
    background: {p.chip_petrol.bg};
    color: {p.chip_petrol.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}
QLabel#Chip_pink {{
    background: {p.chip_pink.bg};
    color: {p.chip_pink.fg};
    border-radius: {RADIUS_SM + 1}px;
    padding: 1px 8px;
    font-size: {FS_SM}px;
    font-weight: {FW_MEDIUM};
}}

/* ---------------------------------------------------------
   Floating save bar  (QFrame#FloatingSaveBar)
   --------------------------------------------------------- */
QFrame#FloatingSaveBar {{
    background: {p.app_fg_strong};
    border-radius: {RADIUS_LG}px;
    /* shadow via QGraphicsDropShadowEffect applied in code */
}}
QFrame#FloatingSaveBar QLabel {{
    color: {p.app_bg};
    font-size: {FS_SM2}px;
}}

/* ---------------------------------------------------------
   Modal  (QDialog#Modal)
   --------------------------------------------------------- */
QDialog#Modal {{
    background: {p.app_elevated};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_XL}px;
}}
QDialog#Modal QLabel#ModalTitle {{
    font-family: "{FONT_DISPLAY}", Georgia, serif;
    font-size: {FS_3XL}px;
    font-weight: {FW_REGULAR};
    color: {p.app_fg_strong};
}}
QDialog#Modal QLabel#ModalEyebrow {{
    font-size: 10px;
    font-weight: {FW_BOLD};
    letter-spacing: 1.5px;
    color: {p.app_fg_subtle};
}}

/* ---------------------------------------------------------
   QToolTip
   --------------------------------------------------------- */
QToolTip {{
    background: {p.app_fg_strong};
    color: {p.app_bg};
    border: none;
    padding: 6px 10px;
    border-radius: {RADIUS_MD}px;
    font-size: {FS_SM2}px;
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

/* ---------------------------------------------------------
   QLabel — generic fallback
   --------------------------------------------------------- */
QLabel {{
    background: transparent;
    color: {p.app_fg};
}}

/* ---------------------------------------------------------
   QFrame dividers  (HLine / VLine via frameShape property)
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

/* ---------------------------------------------------------
   QTabWidget / QTabBar
   --------------------------------------------------------- */
QTabWidget::pane {{
    background: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    border-top-left-radius: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {p.app_fg_muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: {SP_2}px {SP_4}px;
    font-size: {FS_MD}px;
    font-weight: {FW_SEMIBOLD};
    margin-right: {SP_1}px;
    letter-spacing: 0.02em;
}}
QTabBar::tab:hover {{
    color: {p.app_fg};
}}
QTabBar::tab:selected {{
    color: {p.app_accent};
    border-bottom-color: {p.app_accent};
}}

/* ---------------------------------------------------------
   QMenuBar / QMenu
   --------------------------------------------------------- */
QMenuBar {{
    background: {p.app_panel};
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
    background: {p.app_accent_soft};
    color: {p.app_accent};
}}
QMenu {{
    background: {p.app_elevated};
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
    background: {p.app_row_hover};
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
    border: 1px solid {p.app_border_strong};
    border-radius: {RADIUS_SM}px;
    background: {p.app_panel};
}}
QCheckBox::indicator:hover {{
    border-color: {p.app_accent};
}}
QCheckBox::indicator:checked {{
    background: {p.app_accent};
    border-color: {p.app_accent};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {p.app_border_strong};
    border-radius: 8px;
    background: {p.app_panel};
}}
QRadioButton::indicator:hover {{
    border-color: {p.app_accent};
}}
QRadioButton::indicator:checked {{
    background: {p.app_accent};
    border-color: {p.app_accent};
}}

/* ---------------------------------------------------------
   QProgressBar
   --------------------------------------------------------- */
QProgressBar {{
    background: {p.app_border};
    border: none;
    border-radius: {RADIUS_SM}px;
    height: 4px;
    text-align: center;
    font-size: {FS_SM}px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {p.app_accent};
    border-radius: {RADIUS_SM}px;
}}
QProgressBar[variant="success"]::chunk {{
    background: {p.app_success};
}}
QProgressBar[variant="warning"]::chunk {{
    background: {p.app_warning};
}}
QProgressBar[variant="danger"]::chunk {{
    background: {p.app_danger};
}}

/* ---------------------------------------------------------
   QListWidget / QListView
   --------------------------------------------------------- */
QListWidget,
QListView {{
    background: {p.app_panel};
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
    background: {p.app_row_hover};
}}
QListWidget::item:selected,
QListView::item:selected {{
    background: {p.app_row_selected};
    color: {p.app_fg};
}}

/* ---------------------------------------------------------
   QTreeView / QTreeWidget
   --------------------------------------------------------- */
QTreeView,
QTreeWidget {{
    background: {p.app_panel};
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
    background: {p.app_row_hover};
}}
QTreeView::item:selected,
QTreeWidget::item:selected {{
    background: {p.app_row_selected};
    color: {p.app_fg};
}}
QTreeView::branch {{
    background: transparent;
}}

/* ---------------------------------------------------------
   QGroupBox
   --------------------------------------------------------- */
QGroupBox {{
    background: {p.app_panel};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_LG}px;
    margin-top: 14px;
    padding-top: {SP_3}px;
    font-weight: {FW_SEMIBOLD};
    font-size: {FS_MD}px;
    color: {p.app_fg_muted};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {SP_3}px;
    padding: 0 {SP_2}px;
    background: {p.app_panel};
    color: {p.app_fg_muted};
    font-size: {FS_SM}px;
    font-weight: {FW_BOLD};
    letter-spacing: 0.06em;
}}

/* ---------------------------------------------------------
   QToolBar
   --------------------------------------------------------- */
QToolBar {{
    background: {p.app_panel};
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
    background: {p.app_row_hover};
    color: {p.app_fg};
}}
QToolButton:pressed,
QToolButton:checked {{
    background: {p.app_accent_soft};
    color: {p.app_accent};
}}

/* ---------------------------------------------------------
   QDateEdit / QSpinBox / QDoubleSpinBox
   --------------------------------------------------------- */
QDateEdit,
QSpinBox,
QDoubleSpinBox {{
    background: {p.app_panel};
    color: {p.app_fg};
    border: 1px solid {p.app_border};
    border-radius: {RADIUS_MD}px;
    padding: {SP_2}px {SP_3}px;
    font-size: {FS_MD}px;
    min-height: 28px;
}}
QDateEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {{
    border-color: {p.app_accent};
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
   Toast / notification overlay  (QFrame#toast)
   --------------------------------------------------------- */
QFrame#toast {{
    background: {p.app_elevated};
    border: 1px solid {p.app_border};
    border-left: 3px solid {p.app_success};
    border-radius: {RADIUS_MD}px;
    padding: {SP_3}px {SP_4}px;
}}
QFrame#toast[variant="warning"] {{
    border-left: 3px solid {p.app_warning};
}}
QFrame#toast[variant="danger"],
QFrame#toast[variant="error"] {{
    border-left: 3px solid {p.app_danger};
}}
QFrame#toast[variant="info"] {{
    border-left: 3px solid {p.app_info};
}}
QFrame#toast QLabel {{
    background: transparent;
    color: {p.app_fg};
}}
"""
