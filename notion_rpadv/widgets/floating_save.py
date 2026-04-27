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
    FS_MD,
    FW_BOLD,
    FW_MEDIUM,
    SP_1,
    SP_2,
    SP_3,
    SP_4,
    RADIUS_LG,
    RADIUS_XL,
    RADIUS_MD,
)

_BAR_HEIGHT: int = 52
_BAR_MIN_WIDTH: int = 360
_ANIM_DURATION: int = 220


class _CountBadge(QLabel):
    """Pill-shaped badge showing the number of pending edits."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: rgba(181,138,63,0.18);
                color: #7A5C28;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_BOLD};
                border-radius: 11px;
                padding: 0 {SP_2}px;
            }}
            """
        )

    def set_count(self, n: int) -> None:
        unit = "edição" if n == 1 else "edições"
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

        # Rounded top corners only; flat bottom so it sits at the very bottom edge
        self.setStyleSheet(
            f"""
            QFrame#FloatingSaveBar {{
                background-color: #FFFFFF;
                border: 1px solid rgba(20,36,48,0.12);
                border-bottom: none;
                border-top-left-radius: {RADIUS_XL}px;
                border-top-right-radius: {RADIUS_XL}px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, -4)
        shadow.setColor(QColor(10, 15, 20, 55))
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

    def set_count(self, n: int) -> None:
        """Update the pending edit count displayed in the badge."""
        self._count = n
        self._badge.set_count(n)

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
        """Snap the bar to the bottom-centre of the parent widget.

        Call this from the parent's ``resizeEvent``.
        """
        if self.parent() is None:
            return
        pw = self.parent().width()  # type: ignore[union-attr]
        ph = self.parent().height()  # type: ignore[union-attr]
        bar_w = min(max(_BAR_MIN_WIDTH, pw // 2), pw - 64)
        x = (pw - bar_w) // 2
        y = ph - _BAR_HEIGHT
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

        from PySide6.QtCore import QRect
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
        btn = QPushButton("Salvar")
        btn.setFixedHeight(32)
        btn.setMinimumWidth(80)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #104063;
                color: #FFFFFF;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{
                background-color: #0C324D;
            }}
            QPushButton:pressed {{
                background-color: #092840;
            }}
            """
        )
        return btn

    @staticmethod
    def _make_discard_btn() -> QPushButton:
        btn = QPushButton("Descartar")
        btn.setFixedHeight(32)
        btn.setMinimumWidth(90)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: #6F6B68;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: 1px solid #CAD5DD;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{
                background-color: rgba(20,36,48,0.04);
                color: #3F4751;
            }}
            QPushButton:pressed {{
                background-color: rgba(20,36,48,0.08);
            }}
            """
        )
        return btn
