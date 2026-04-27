"""Cmd+K command palette overlay."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QWidget,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QPainter,
    QPaintEvent,
)

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FS_SM,
    FS_MD,
    FS_LG,
    FW_BOLD,
    FW_MEDIUM,
    SP_1,
    SP_3,
    SP_4,
    RADIUS_XL,
    RADIUS_MD,
)

_CARD_WIDTH: int = 480
_MAX_CARD_HEIGHT: int = 520
_SECTION_HEADER_HEIGHT: int = 28
_ITEM_HEIGHT: int = 44

# Internal data role for storing the action id on list items
_ACTION_ID_ROLE: int = Qt.ItemDataRole.UserRole
_ACTION_SECTION_ROLE: int = Qt.ItemDataRole.UserRole + 1
_IS_HEADER_ROLE: int = Qt.ItemDataRole.UserRole + 2


class _SearchInput(QLineEdit):
    """Styled search input for the command palette."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Buscar ações, processos, atalhos…")
        self.setFixedHeight(44)
        self.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: transparent;
                color: #142430;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_LG}px;
                font-weight: {FW_MEDIUM};
                border: none;
                border-bottom: 1px solid rgba(20,36,48,0.10);
                border-radius: 0;
                padding: 0 {SP_4}px;
            }}
            QLineEdit:focus {{
                outline: none;
            }}
            """
        )
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)


class CommandPalette(QDialog):
    """Full-screen overlay with search input and a filtered action list.

    Opens with :meth:`show_palette` and emits :attr:`action_selected` with
    the ``action_id`` string when the user picks an entry.

    Parameters
    ----------
    parent:
        The main application window.  The palette sizes itself to cover it
        fully.

    Action dict shape::

        {
            "id": "new_process",
            "label": "Novo processo",
            "shortcut": "Ctrl+N",   # optional
            "section": "Processos",
        }
    """

    action_selected: Signal = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        self._actions: list[dict[str, str]] = []
        self._filtered: list[dict[str, str]] = []

        # Outer full-screen layout — clicking outside the card closes the dialog
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        outer.addSpacing(80)  # vertical offset from top

        # Card
        self._card = QFrame()
        self._card.setObjectName("CmdCard")
        self._card.setFixedWidth(_CARD_WIDTH)
        self._card.setMaximumHeight(_MAX_CARD_HEIGHT)
        self._card.setStyleSheet(
            f"""
            QFrame#CmdCard {{
                background-color: #FFFFFF;
                border-radius: {RADIUS_XL}px;
                border: 1px solid rgba(20,36,48,0.12);
            }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(10, 15, 20, 80))
        self._card.setGraphicsEffect(shadow)
        outer.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Search input
        self._search = _SearchInput(self._card)
        self._search.textChanged.connect(self._on_search_changed)
        card_layout.addWidget(self._search)

        # Results list
        self._list = QListWidget(self._card)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                padding: {SP_1}px 0;
            }}
            QListWidget::item {{
                background-color: transparent;
                color: #142430;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                font-weight: {FW_MEDIUM};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
                height: {_ITEM_HEIGHT}px;
            }}
            QListWidget::item:selected,
            QListWidget::item:hover {{
                background-color: rgba(16,64,99,0.06);
                color: #0C324D;
            }}
            QListWidget::item:selected {{
                background-color: rgba(16,64,99,0.10);
            }}
            """
        )
        self._list.itemActivated.connect(self._on_item_activated)
        self._list.setMaximumHeight(_MAX_CARD_HEIGHT - 44 - 8)
        card_layout.addWidget(self._list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_actions(self, actions: list[dict[str, str]]) -> None:
        """Replace the full action list.

        Each dict must have ``"id"`` and ``"label"``; ``"shortcut"`` and
        ``"section"`` are optional.
        """
        self._actions = actions
        self._rebuild_list(self._actions)

    def show_palette(self) -> None:
        """Size the overlay to the parent window and open it."""
        if self.parent() is not None:
            pw = self.parent()
            self.resize(pw.width(), pw.height())  # type: ignore[union-attr]
        self._search.clear()
        self._rebuild_list(self._actions)
        self.show()
        self._search.setFocus()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_current()
            return
        if key == Qt.Key.Key_Down:
            self._move_selection(1)
            return
        if key == Qt.Key.Key_Up:
            self._move_selection(-1)
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        """Clicking outside the card closes the palette."""
        # If click is not within the card geometry, close
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent):
            card_rect = self._card.geometry()
            if not card_rect.contains(event.pos()):
                self.reject()
                return
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 15, 20, 100))
        painter.end()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self._rebuild_list(self._actions)
            return
        filtered = [
            a for a in self._actions
            if query in a.get("label", "").lower()
            or query in a.get("section", "").lower()
        ]
        self._rebuild_list(filtered)

    def _rebuild_list(self, actions: list[dict[str, str]]) -> None:
        self._list.clear()
        if not actions:
            empty = QListWidgetItem("Nenhuma ação encontrada")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(QColor("#9FB3C1"))
            self._list.addItem(empty)
            return

        # Group by section
        sections: dict[str, list[dict[str, str]]] = {}
        for action in actions:
            section = action.get("section", "Geral")
            sections.setdefault(section, []).append(action)

        for section_name, items in sections.items():
            # Section header (non-selectable)
            header = QListWidgetItem(section_name.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setForeground(QColor("#9FB3C1"))
            header.setSizeHint(QSize(_CARD_WIDTH, _SECTION_HEADER_HEIGHT))
            font = QFont(FONT_BODY)
            font.setPixelSize(FS_SM)
            font.setWeight(QFont.Weight(FW_BOLD))
            header.setFont(font)
            header.setData(_IS_HEADER_ROLE, True)
            self._list.addItem(header)

            for action in items:
                item = self._make_action_item(action)
                self._list.addItem(item)

        # Auto-select first real item
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is not None and it.data(_IS_HEADER_ROLE) is not True:
                self._list.setCurrentItem(it)
                break

    def _make_action_item(self, action: dict[str, str]) -> QListWidgetItem:
        label = action.get("label", "")
        shortcut = action.get("shortcut", "")
        display = f"{label}   {shortcut}" if shortcut else label

        item = QListWidgetItem(display)
        item.setSizeHint(QSize(_CARD_WIDTH, _ITEM_HEIGHT))
        item.setData(_ACTION_ID_ROLE, action.get("id", ""))
        item.setData(_IS_HEADER_ROLE, False)

        font = QFont(FONT_BODY)
        font.setPixelSize(FS_MD)
        font.setWeight(QFont.Weight(FW_MEDIUM))
        item.setFont(font)

        return item

    def _activate_current(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        if item.data(_IS_HEADER_ROLE):
            return
        action_id: str = item.data(_ACTION_ID_ROLE) or ""
        if action_id:
            self.action_selected.emit(action_id)
            self.accept()

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        if item.data(_IS_HEADER_ROLE):
            return
        action_id: str = item.data(_ACTION_ID_ROLE) or ""
        if action_id:
            self.action_selected.emit(action_id)
            self.accept()

    def _move_selection(self, delta: int) -> None:
        current_row = self._list.currentRow()
        count = self._list.count()
        row = current_row + delta
        # Skip header items
        for _ in range(count):
            if row < 0:
                row = count - 1
            elif row >= count:
                row = 0
            item = self._list.item(row)
            if item is not None and not item.data(_IS_HEADER_ROLE):
                self._list.setCurrentRow(row)
                return
            row += delta
