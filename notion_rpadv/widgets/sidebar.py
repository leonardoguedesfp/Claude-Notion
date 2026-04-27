"""Main navigation sidebar."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QSizePolicy,
    QSpacerItem,
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QFont, QColor, QPalette

from notion_rpadv.theme.tokens import (
    LIGHT,
    DARK,
    Palette,
    FONT_BODY,
    FS_SM,
    FS_SM2,
    FS_MD,
    FS_LG,
    FS_XL,
    FW_BOLD,
    FW_MEDIUM,
    SP_1,
    SP_2,
    SP_3,
    SP_4,
    RADIUS_MD,
    RADIUS_LG,
)
from notion_rpadv.widgets.person_chip import PersonChip

# ---------------------------------------------------------------------------
# Navigation item definitions
# ---------------------------------------------------------------------------

NAV_ITEMS: list[tuple[str, str, str]] = [
    ("dashboard", "Dashboard",   "⊞"),   # ⊞
    ("processos", "Processos",   "⚖"),   # ⚖
    ("clientes",  "Clientes",    "\U0001f465"),  # 👥
    ("tarefas",   "Tarefas",     "✓"),   # ✓
    ("catalogo",  "Cat\xe1logo", "\U0001f4cb"),  # 📋
]

BOTTOM_ITEMS: list[tuple[str, str, str]] = [
    ("importar", "Importar",       "↑"),      # ↑
    ("logs",     "Logs",           "\U0001f4dd"),  # 📝
    ("config",   "Configura\xe7\xf5es", "⚙"), # ⚙
]

_SIDEBAR_WIDTH: int = 220
_ITEM_HEIGHT: int = 40

# Navy used for sidebar — always the same regardless of app theme
_NAV_BG: str = "#0C324D"
_NAV_FG: str = "#EDEAE4"
_NAV_FG_MUTED: str = "rgba(237,234,228,0.60)"
_NAV_HOVER: str = "rgba(237,234,228,0.08)"
_NAV_ACTIVE: str = "rgba(237,234,228,0.14)"


class SidebarItem(QPushButton):
    """A single navigation button in the sidebar.

    Displays a unicode icon followed by a text label.  Active state is
    controlled externally via :meth:`set_active`.
    """

    def __init__(
        self,
        page_id: str,
        label: str,
        icon: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._page_id = page_id
        self._active: bool = False
        self._icon_char = icon
        self._label_text = label

        self.setText(f"  {icon}  {label}")
        self.setFixedHeight(_ITEM_HEIGHT)
        self.setFlat(True)
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._refresh_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def page_id(self) -> str:
        return self._page_id

    def set_active(self, active: bool) -> None:
        """Toggle the active highlight."""
        self._active = active
        self._refresh_style()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_style(self) -> None:
        bg = _NAV_ACTIVE if self._active else "transparent"
        fw = FW_BOLD if self._active else FW_MEDIUM
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg};
                color: {_NAV_FG};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                font-weight: {fw};
                text-align: left;
                padding: 0 {SP_3}px;
                border: none;
                border-radius: {RADIUS_MD}px;
            }}
            QPushButton:hover {{
                background-color: {_NAV_HOVER if not self._active else _NAV_ACTIVE};
            }}
            QPushButton:pressed {{
                background-color: {_NAV_ACTIVE};
            }}
            """
        )


class _SectionDivider(QFrame):
    """Thin horizontal line used to separate nav groups."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setFixedHeight(1)
        self.setStyleSheet("background-color: rgba(237,234,228,0.12); border: none;")


class _LogoBlock(QWidget):
    """Displays the RP + ADVOCACIA logo in cream on the navy sidebar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP_4, SP_4, SP_4, SP_3)
        layout.setSpacing(0)

        rp_label = QLabel("RP")
        rp_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        rp_label.setStyleSheet(
            f"""
            QLabel {{
                color: {_NAV_FG};
                font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif;
                font-size: 28px;
                font-weight: {FW_BOLD};
                background: transparent;
                border: none;
                letter-spacing: 2px;
            }}
            """
        )

        adv_label = QLabel("ADVOCACIA")
        adv_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        adv_label.setStyleSheet(
            f"""
            QLabel {{
                color: {_NAV_FG_MUTED};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                letter-spacing: 3px;
                background: transparent;
                border: none;
            }}
            """
        )

        layout.addWidget(rp_label)
        layout.addWidget(adv_label)


class _UserBlock(QWidget):
    """Bottom area: avatar chip + name for the logged-in user."""

    def __init__(
        self,
        user: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(SP_3, SP_2, SP_3, SP_2)
        self._layout.setSpacing(SP_2)

        initials, name = self._parse_user(user)

        # Avatar slightly smaller for the footer
        self._chip = PersonChip(
            initials=initials,
            name=name,
            color="#104063",
            dark=True,
            parent=self,
        )
        self._layout.addWidget(self._chip)
        self._layout.addStretch()

        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(48)

    def update_user(self, user: dict[str, str]) -> None:
        initials, name = self._parse_user(user)
        self._chip.set_initials(initials)
        self._chip.set_name(name)

    @staticmethod
    def _parse_user(user: dict[str, str]) -> tuple[str, str]:
        name: str = user.get("name", "")
        initials: str = user.get("initials", "")
        if not initials and name:
            parts = name.split()
            initials = "".join(p[0] for p in parts[:2]).upper()
        return initials or "?", name


class Sidebar(QWidget):
    """Fixed-width (220 px) navy sidebar with logo, navigation, and user area.

    Emits :attr:`page_changed` with the ``page_id`` string whenever the user
    clicks a navigation item.

    Parameters
    ----------
    user:
        Dict with at least ``"name"`` and optionally ``"initials"`` keys.
    dark:
        Passed through to child widgets that adapt to the app theme; the
        sidebar itself is always navy.
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
        self._items: dict[str, SidebarItem] = {}
        self._active_id: str = ""

        self.setFixedWidth(_SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            f"""
            QWidget#Sidebar {{
                background-color: {_NAV_BG};
                border: none;
            }}
            """
        )
        self.setObjectName("Sidebar")

        root = QVBoxLayout(self)
        root.setContentsMargins(SP_2, 0, SP_2, SP_2)
        root.setSpacing(0)

        # Logo
        root.addWidget(_LogoBlock())
        root.addWidget(_SectionDivider())
        root.addSpacing(SP_2)

        # Main nav items
        for page_id, label, icon in NAV_ITEMS:
            btn = SidebarItem(page_id, label, icon, parent=self)
            btn.clicked.connect(self._on_item_clicked)
            self._items[page_id] = btn
            root.addWidget(btn)

        root.addStretch()
        root.addWidget(_SectionDivider())
        root.addSpacing(SP_1)

        # Bottom nav items
        for page_id, label, icon in BOTTOM_ITEMS:
            btn = SidebarItem(page_id, label, icon, parent=self)
            btn.clicked.connect(self._on_item_clicked)
            self._items[page_id] = btn
            root.addWidget(btn)

        root.addSpacing(SP_2)
        root.addWidget(_SectionDivider())

        # User block at very bottom
        self._user_block = _UserBlock(user, parent=self)
        root.addWidget(self._user_block)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_active(self, page_id: str) -> None:
        """Highlight the item matching *page_id* and deactivate others."""
        if self._active_id:
            old = self._items.get(self._active_id)
            if old is not None:
                old.set_active(False)
        self._active_id = page_id
        new = self._items.get(page_id)
        if new is not None:
            new.set_active(True)

    def set_user(self, user: dict[str, str]) -> None:
        """Update the logged-in user display at the bottom of the sidebar."""
        self._user_block.update_user(user)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_clicked(self) -> None:
        sender = self.sender()
        if isinstance(sender, SidebarItem):
            self.set_active(sender.page_id)
            self.page_changed.emit(sender.page_id)
