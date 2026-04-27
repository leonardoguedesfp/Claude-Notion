"""Main navigation sidebar — matches the HTML prototype exactly."""
from __future__ import annotations

import pathlib

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPainter, QColor, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from notion_rpadv.theme.tokens import (
    FONT_MONO,
    FW_REGULAR,
    FW_SEMIBOLD,
)

# ---------------------------------------------------------------------------
# Asset paths
# ---------------------------------------------------------------------------

_ASSETS_DIR: pathlib.Path = pathlib.Path(__file__).parent.parent / "assets"

# ---------------------------------------------------------------------------
# Design constants — mirror the CSS/JSX prototype verbatim
# ---------------------------------------------------------------------------

_SIDEBAR_WIDTH: int = 220
_NAV_BG: str = "#0C324D"
_CREAM: str = "#EDEAE4"
_CREAM_MUTED: str = "rgba(237,234,228,0.55)"
_HOVER_BG: str = "rgba(237,234,228,0.06)"
_ACTIVE_BG: str = "rgba(237,234,228,0.12)"
_BRAND_BORDER: str = "rgba(237,234,228,0.08)"
_BADGE_BG: str = "#B58A3F"
_BADGE_FG: str = "#1F1E1D"

# ---------------------------------------------------------------------------
# Nav item definitions
# ---------------------------------------------------------------------------

# (page_id, label, shortcut_or_None)  — icons handled below
_MAIN_NAV: list[tuple[str, str, str | None]] = [
    ("dashboard", "Dashboard",       "⌘1"),
    ("processos", "Processos",       "⌘2"),
    ("clientes",  "Clientes",        "⌘3"),
    ("tarefas",   "Tarefas",         "⌘4"),
    ("catalogo",  "Catálogo",        "⌘5"),
]

_DADOS_NAV: list[tuple[str, str, str | None]] = [
    ("importar", "Importar planilha", None),
    ("logs",     "Logs",              None),
]

_BOTTOM_NAV: list[tuple[str, str, str | None]] = [
    ("config", "Configurações", None),
]

# Unicode icon per page_id
_ICONS: dict[str, str] = {
    "dashboard": "⊞",
    "processos": "⚖",
    "clientes":  "👥",
    "tarefas":   "✓",
    "catalogo":  "📋",
    "importar":  "↑",
    "logs":      "📝",
    "config":    "⚙",
}


# ---------------------------------------------------------------------------
# SidebarItem
# ---------------------------------------------------------------------------

class SidebarItem(QWidget):
    """A single navigation row: [icon] [label/flex] [shortcut | badge].

    Active state is shown with a 2 px cream left border accent painted via
    :meth:`paintEvent` plus the semi-transparent cream background.
    """

    clicked: Signal = Signal(str)  # emits page_id

    def __init__(
        self,
        page_id: str,
        label: str,
        shortcut: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._page_id = page_id
        self._active: bool = False
        self._badge_count: int = 0

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(32)  # 7px top + 7px bottom padding + 13px font ≈ 32px

        # ── layout ──────────────────────────────────────────────────────────
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 7, 16, 7)
        row.setSpacing(10)

        # Icon label (16×16 fixed)
        self._icon_label = QLabel(_ICONS.get(page_id, "·"))
        self._icon_label.setFixedSize(16, 16)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet(
            f"color: {_CREAM}; background: transparent; font-size: 13px; opacity: 0.85;"
        )
        row.addWidget(self._icon_label)

        # Nav label (flex: 1)
        self._nav_label = QLabel(label)
        self._nav_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._nav_label.setStyleSheet(
            f"color: {_CREAM}; background: transparent; font-size: 13px;"
        )
        row.addWidget(self._nav_label)

        # Shortcut label (hidden when badge is showing)
        self._shortcut_label: QLabel | None = None
        if shortcut is not None:
            self._shortcut_label = QLabel(shortcut)
            self._shortcut_label.setStyleSheet(
                f"color: {_CREAM_MUTED}; background: transparent;"
                f" font-family: {FONT_MONO}, monospace; font-size: 10px;"
            )
            row.addWidget(self._shortcut_label)

        # Badge label (hidden by default)
        self._badge_label = QLabel("")
        self._badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge_label.setStyleSheet(
            f"color: {_BADGE_FG}; background-color: {_BADGE_BG};"
            " font-size: 10px; font-weight: 700;"
            " padding: 1px 6px; border-radius: 8px;"
        )
        self._badge_label.hide()
        row.addWidget(self._badge_label)

        self._apply_font_weight()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def page_id(self) -> str:
        return self._page_id

    def set_active(self, active: bool) -> None:
        """Toggle active highlight (background + left border accent + bold)."""
        self._active = active
        self._apply_font_weight()
        self.update()  # trigger repaint for left border

    def set_badge(self, count: int) -> None:
        """Show *count* as a gold badge (hides shortcut label when count > 0)."""
        self._badge_count = count
        if count > 0:
            self._badge_label.setText(str(count))
            self._badge_label.show()
            if self._shortcut_label is not None:
                self._shortcut_label.hide()
        else:
            self._badge_label.hide()
            if self._shortcut_label is not None:
                self._shortcut_label.show()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        self.clicked.emit(self._page_id)

    def enterEvent(self, event: object) -> None:  # type: ignore[override]
        if not self._active:
            self.update()

    def leaveEvent(self, event: object) -> None:  # type: ignore[override]
        self.update()

    # ------------------------------------------------------------------
    # Paint: background + 2 px left accent when active
    # ------------------------------------------------------------------

    def paintEvent(self, event: object) -> None:  # type: ignore[override]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect()

        # Background
        if self._active:
            painter.fillRect(rect, QColor(237, 234, 228, int(0.12 * 255)))
        elif self.underMouse():
            painter.fillRect(rect, QColor(237, 234, 228, int(0.06 * 255)))

        # 2 px cream left border when active
        if self._active:
            painter.fillRect(0, 0, 2, rect.height(), QColor(_CREAM))

        painter.end()

        # Let Qt draw children (labels) on top
        super().paintEvent(event)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_font_weight(self) -> None:
        weight = FW_SEMIBOLD if self._active else FW_REGULAR
        self._nav_label.setStyleSheet(
            f"color: {_CREAM}; background: transparent;"
            f" font-size: 13px; font-weight: {weight};"
        )


# ---------------------------------------------------------------------------
# Section label
# ---------------------------------------------------------------------------

class _SectionLabel(QLabel):
    """CSS: .sidebar-label"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color: {_CREAM_MUTED}; background: transparent;"
            " font-size: 9.5px; font-weight: 700;"
            " letter-spacing: 0.16em; text-transform: uppercase;"
            " padding: 4px 16px 8px 16px;"
        )


# ---------------------------------------------------------------------------
# Brand block
# ---------------------------------------------------------------------------

class _BrandBlock(QWidget):
    """CSS: .sidebar-brand — logo image + two-line text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)  # 18px top + 16px bottom padding + content

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 18, 16, 16)
        row.setSpacing(10)

        # Symbol image — 22px height, aspect ratio preserved
        img_label = QLabel()
        img_label.setFixedSize(QSize(40, 22))  # max width; height 22px
        img_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        img_path = _ASSETS_DIR / "symbol-cream.png"
        pix = QPixmap(str(img_path))
        if not pix.isNull():
            pix = pix.scaledToHeight(22, Qt.TransformationMode.SmoothTransformation)
        img_label.setPixmap(pix)
        img_label.setScaledContents(False)
        img_label.setStyleSheet("background: transparent;")
        row.addWidget(img_label)

        # Text block: two stacked labels
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        title = QLabel("Notion RPADV")
        title.setStyleSheet(
            f"color: {_CREAM}; background: transparent;"
            " font-size: 10px; font-weight: 700;"
            " letter-spacing: 0.14em;"
        )
        text_col.addWidget(title)

        sub = QLabel("Ricardo Passos Advocacia")
        sub.setStyleSheet(
            f"color: {_CREAM_MUTED}; background: transparent;"
            " font-size: 9px; font-weight: 400;"
            " letter-spacing: 0.08em;"
        )
        text_col.addWidget(sub)

        row.addLayout(text_col)
        row.addStretch()

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        rect = self.rect()
        # Bottom border: 1px rgba(237,234,228,0.08)
        painter.setPen(QColor(237, 234, 228, int(0.08 * 255)))
        painter.drawLine(0, rect.height() - 1, rect.width(), rect.height() - 1)
        painter.end()
        super().paintEvent(event)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

class Sidebar(QWidget):
    """Fixed-width (220 px) navy sidebar matching the HTML prototype.

    Signals
    -------
    page_changed : Signal(str)
        Emitted with the ``page_id`` string when the user clicks a nav item.

    Public API
    ----------
    set_active(page_id)
        Highlight the named nav item and clear any previous one.
    set_user(user)
        Update the logged-in user (currently unused visually; reserved for
        a future user block implementation).
    set_urgent_count(n)
        Update the tarefas badge; hides it when *n* == 0.
    """

    page_changed: Signal = Signal(str)

    def __init__(
        self,
        user: dict[str, str],
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark = dark
        self._user = user
        self._items: dict[str, SidebarItem] = {}
        self._active_id: str = ""

        self.setFixedWidth(_SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setObjectName("Sidebar")
        # Background is always navy regardless of app theme
        self.setStyleSheet(f"QWidget#Sidebar {{ background-color: {_NAV_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Brand block ──────────────────────────────────────────────────
        root.addWidget(_BrandBlock())

        # ── Main nav (no section label) ───────────────────────────────────
        root.addSpacing(4)
        for page_id, label, shortcut in _MAIN_NAV:
            item = SidebarItem(page_id, label, shortcut, parent=self)
            item.clicked.connect(self._on_item_clicked)
            self._items[page_id] = item
            root.addWidget(item)

        # ── DADOS section ────────────────────────────────────────────────
        root.addSpacing(8)
        root.addWidget(_SectionLabel("Dados"))
        for page_id, label, shortcut in _DADOS_NAV:
            item = SidebarItem(page_id, label, shortcut, parent=self)
            item.clicked.connect(self._on_item_clicked)
            self._items[page_id] = item
            root.addWidget(item)

        # ── Push remaining items to the bottom ───────────────────────────
        root.addStretch(1)

        # ── Bottom nav ───────────────────────────────────────────────────
        for page_id, label, shortcut in _BOTTOM_NAV:
            item = SidebarItem(page_id, label, shortcut, parent=self)
            item.clicked.connect(self._on_item_clicked)
            self._items[page_id] = item
            root.addWidget(item)

        root.addSpacing(8)

    # ------------------------------------------------------------------
    # paintEvent — always fill with navy background
    # ------------------------------------------------------------------

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(_NAV_BG))
        painter.end()
        super().paintEvent(event)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_active(self, page_id: str) -> None:
        """Highlight *page_id*, deactivating the previously active item."""
        if self._active_id:
            old = self._items.get(self._active_id)
            if old is not None:
                old.set_active(False)
        self._active_id = page_id
        new = self._items.get(page_id)
        if new is not None:
            new.set_active(True)

    def set_user(self, user: dict[str, str]) -> None:
        """Store updated user info (reserved for future user-block widget)."""
        self._user = user

    def set_urgent_count(self, n: int) -> None:
        """Show or hide the urgent-task badge on the Tarefas nav item."""
        tarefas = self._items.get("tarefas")
        if tarefas is not None:
            tarefas.set_badge(n)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_clicked(self, page_id: str) -> None:
        self.set_active(page_id)
        self.page_changed.emit(page_id)
