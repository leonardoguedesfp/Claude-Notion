"""Floating save bar that appears when there are unsaved changes."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QWidget,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QByteArray, QEasingCurve
from PySide6.QtGui import QColor

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    SP_2,
    SP_3,
    SP_4,
    RADIUS_XL,
    RADIUS_MD,
)

_BAR_HEIGHT: int = 52
_BAR_MIN_WIDTH: int = 360
_ANIM_DURATION: int = 220
# §4.1 Bottom-right margin
_BAR_MARGIN: int = 16


class _CountBadge(QLabel):
    """Pill-shaped badge showing the number of pending edits and base name."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: rgba(255,217,90,0.22);
                color: #F5DC7A;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_BOLD};
                border-radius: 11px;
                padding: 0 {SP_2}px;
            }}
            """
        )

    def set_count(self, n: int, base_name: str | None = None) -> None:
        # §4.2 include base name in badge text
        unit = "alteração" if n == 1 else "alterações"
        if base_name:
            self.setText(f" {n} {unit} em {base_name} ")
        else:
            self.setText(f" {n} {unit} pendentes ")
        self.adjustSize()


class FloatingSaveBar(QFrame):
    """Shows 'N edições pendentes' + Salvar + Descartar buttons.

    The bar floats over the content area.  Position it by calling
    :meth:`reposition` whenever the parent resizes, or manage it yourself
    with absolute geometry.

    Signals
    -------
    save_clicked:
        Emitted when the user clicks 'Salvar'.
    discard_clicked:
        Emitted when the user clicks 'Descartar'.

    Usage::

        bar = FloatingSaveBar(parent=content_widget)
        bar.save_clicked.connect(on_save)
        bar.discard_clicked.connect(on_discard)
        bar.set_count(3)
        bar.show_bar()
    """

    save_clicked: Signal = Signal()
    discard_clicked: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FloatingSaveBar")
        self.setFixedHeight(_BAR_HEIGHT)
        self.setMinimumWidth(_BAR_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # §4.3 navy background — rounded pill floating above content
        self.setStyleSheet(
            f"""
            QFrame#FloatingSaveBar {{
                background-color: #0C324D;
                border: none;
                border-radius: {RADIUS_XL}px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(10, 15, 20, 90))
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SP_4, 0, SP_4, 0)
        layout.setSpacing(SP_3)

        # Count badge
        self._badge = _CountBadge(self)
        layout.addWidget(self._badge)

        layout.addStretch()

        # Discard button
        self._discard_btn = self._make_discard_btn()
        self._discard_btn.clicked.connect(self.discard_clicked)
        layout.addWidget(self._discard_btn)

        # Save button
        self._save_btn = self._make_save_btn()
        self._save_btn.clicked.connect(self.save_clicked)
        layout.addWidget(self._save_btn)

        self._count: int = 0
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_count(self, n: int, base_name: str | None = None) -> None:
        """Update the pending edit count; §4.2 optionally include base name."""
        self._count = n
        self._badge.set_count(n, base_name)

    def show_bar(self) -> None:
        """Slide the bar into view with an upward animation."""
        if self.isVisible():
            return
        self.show()
        self._animate(show=True)

    def hide_bar(self) -> None:
        """Slide the bar out of view with a downward animation."""
        if not self.isVisible():
            return
        anim = self._animate(show=False)
        if anim is not None:
            anim.finished.connect(self.hide)

    def reposition(self) -> None:
        """Snap the bar to the bottom-right of the parent widget (§4.1).

        Call this from the parent's ``resizeEvent``.
        """
        if self.parent() is None:
            return
        pw = self.parent().width()  # type: ignore[union-attr]
        ph = self.parent().height()  # type: ignore[union-attr]
        bar_w = min(max(_BAR_MIN_WIDTH, pw // 2), pw - 64)
        # §4.1 bottom-right with 16px margin
        x = pw - bar_w - _BAR_MARGIN
        y = ph - _BAR_HEIGHT - _BAR_MARGIN
        self.setGeometry(x, y, bar_w, _BAR_HEIGHT)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _animate(self, show: bool) -> QPropertyAnimation | None:
        if self.parent() is None:
            return None
        ph = self.parent().height()  # type: ignore[union-attr]
        hidden_y = ph
        visible_y = ph - _BAR_HEIGHT
        start_y = visible_y if show else hidden_y
        end_y = hidden_y if show else visible_y  # wait — reversed

        # Correct: when showing, go from below → visible_y
        start_y = ph if show else visible_y
        end_y = visible_y if show else ph

        start_rect = self.geometry()
        start_rect.moveTop(start_y)
        end_rect = self.geometry()
        end_rect.moveTop(end_y)

        anim = QPropertyAnimation(self, QByteArray(b"geometry"), self)
        anim.setDuration(_ANIM_DURATION)
        anim.setEasingCurve(
            QEasingCurve.Type.OutCubic if show else QEasingCurve.Type.InCubic
        )
        anim.setStartValue(start_rect)
        anim.setEndValue(end_rect)
        anim.start()
        return anim

    @staticmethod
    def _make_save_btn() -> QPushButton:
        # §4.3 Save = cream/white on navy bar — visually primary
        btn = QPushButton("Salvar")
        btn.setFixedHeight(32)
        btn.setMinimumWidth(80)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #EDEAE4;
                color: #0C324D;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_BOLD};
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{
                background-color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #CAD5DD;
            }}
            """
        )
        return btn

    @staticmethod
    def _make_discard_btn() -> QPushButton:
        # §4.3 Discard = ghost — no border, muted cream text
        btn = QPushButton("Descartar")
        btn.setFixedHeight(32)
        btn.setMinimumWidth(90)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: rgba(237,234,228,0.65);
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{
                background-color: rgba(237,234,228,0.08);
                color: rgba(237,234,228,0.90);
            }}
            QPushButton:pressed {{
                background-color: rgba(237,234,228,0.12);
            }}
            """
        )
        return btn
