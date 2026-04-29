"""Avatar chip for Notion people fields."""
from __future__ import annotations


from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import (
    QPainter,
    QColor,
    QFont,
    QPaintEvent,
)

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FS_SM2,
    FW_MEDIUM,
    FW_BOLD,
    SP_2,
    resolve_person_avatar_color,
)

_AVATAR_SIZE: int = 28        # diameter of the circle
_AVATAR_FONT_SIZE: int = 10   # initials font size inside circle


class _AvatarCircle(QWidget):
    """Internal widget: draws a filled circle with 1-2 initials letters."""

    def __init__(
        self,
        initials: str,
        bg_color: str = "#104063",
        fg_color: str = "#EDEAE4",
        size: int = _AVATAR_SIZE,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._initials = initials[:2].upper()
        self._bg_color = QColor(bg_color)
        self._fg_color = QColor(fg_color)
        self._size = size
        self.setFixedSize(QSize(size, size))

    def set_initials(self, initials: str) -> None:
        self._initials = initials[:2].upper()
        self.update()

    def set_colors(self, bg: str, fg: str) -> None:
        self._bg_color = QColor(bg)
        self._fg_color = QColor(fg)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Circle background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg_color)
        rect = QRect(0, 0, self._size, self._size)
        painter.drawEllipse(rect)

        # Initials text
        font = QFont(FONT_BODY)
        font.setPixelSize(_AVATAR_FONT_SIZE)
        font.setWeight(QFont.Weight(FW_BOLD))
        painter.setFont(font)
        painter.setPen(self._fg_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._initials)

        painter.end()


class PersonChip(QWidget):
    """Shows initials in a circle + optional name label to the right.

    Usage::

        chip = PersonChip("JD", name="João Dias")               # cor auto
        chip = PersonChip("MF", name="", color="#395A5A")       # cor manual

    Parameters
    ----------
    initials:
        1 or 2 letters to display inside the circle.
    name:
        Optional full name shown to the right of the avatar. Pass ``""`` to
        display the avatar only.
    color:
        Background hex colour for the avatar circle. Quando ``None`` (default),
        resolve via ``resolve_person_avatar_color(initials)`` — cada usuário
        ganha cor estável da paleta brand conforme PERSON_CHIP_COLORS em
        ``colors_overrides.py``.

    Round 3a: kwarg ``dark`` removido — paleta única LIGHT.
    Round 3b-2: cor default agora vem do override map (cor por usuário).
    """

    def __init__(
        self,
        initials: str,
        name: str = "",
        color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        if color is None:
            bg_color, fg_color = resolve_person_avatar_color(initials)
        else:
            bg_color = color
            fg_color = "#EDEAE4"  # cream — readable on all brand families

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SP_2)

        self._avatar = _AvatarCircle(
            initials, bg_color=bg_color, fg_color=fg_color, parent=self
        )
        layout.addWidget(self._avatar)

        self._name_label: QLabel | None = None
        if name:
            self._name_label = self._make_name_label(name)
            layout.addWidget(self._name_label)

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(_AVATAR_SIZE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_initials(self, initials: str) -> None:
        """Update the avatar initials."""
        self._avatar.set_initials(initials)

    def set_name(self, name: str) -> None:
        """Update the name label text (creates the label if it didn't exist)."""
        if self._name_label is None:
            self._name_label = self._make_name_label(name)
            self.layout().addWidget(self._name_label)  # type: ignore[union-attr]
        else:
            self._name_label.setText(name)
            self._name_label.setVisible(bool(name))

    def set_color(self, bg: str, fg: str = "#EDEAE4") -> None:
        """Change the avatar circle colours."""
        self._avatar.set_colors(bg, fg)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_name_label(name: str) -> QLabel:
        # Round 3a: paleta única LIGHT — texto sempre #142430.
        label = QLabel(name)
        text_color = "#142430"
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {text_color};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        return label
