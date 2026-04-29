"""Chip / pill badge widget for select values."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from notion_rpadv.theme.tokens import (
    chip_palette,
    FONT_BODY,
    FS_SM,
    FW_MEDIUM,
    RADIUS_LG,
    SP_2,
)


class Chip(QLabel):
    """Renders a colored pill label for a select value.

    Usage::

        chip = Chip("Ativo", color="green")

    The widget sizes itself to its text content but caps the visible text with
    an ellipsis when placed inside a constrained layout.

    Round 3a: kwarg ``dark`` removido — paleta única LIGHT.
    """

    _PADDING_H: int = SP_2  # 8 px horizontal padding each side
    _HEIGHT: int = 20        # fixed pixel height

    def __init__(
        self,
        text: str,
        color: str = "default",
        parent: QLabel | None = None,
    ) -> None:
        super().__init__(parent)

        self._color = color
        self._full_text = text

        self.setObjectName(f"Chip_{color}")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(self._HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )

        self._apply_style()
        self._apply_text()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        """Update the displayed text and re-elide if needed."""
        self._full_text = text
        self._apply_text()

    def set_color(self, color: str) -> None:
        """Change the semantic colour key."""
        self._color = color
        self.setObjectName(f"Chip_{color}")
        self._apply_style()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        palette = chip_palette(self._color)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {palette.bg};
                color: {palette.fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                border-radius: {RADIUS_LG}px;
                padding: 0px {self._PADDING_H}px;
            }}
            """
        )

    def _apply_text(self) -> None:
        """Set elided text so the chip never overflows its width."""
        fm = QFontMetrics(self.font())
        # allow up to 160 px; fall back to full text if widget is unconstrained
        max_w = max(self.width() - 2 * self._PADDING_H, 100)
        elided = fm.elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, max_w
        )
        super().setText(elided)
        if elided != self._full_text:
            self.setToolTip(self._full_text)
        else:
            self.setToolTip("")

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._apply_text()
