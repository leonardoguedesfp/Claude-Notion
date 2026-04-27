"""Toast notification widget (slides in from bottom-right)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QWidget,
    QSizePolicy,
    QApplication,
)
from PySide6.QtCore import (
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Qt,
    QPoint,
    QByteArray,
)
from PySide6.QtGui import QColor, QFont

from notion_rpadv.theme.tokens import (
    LIGHT,
    FONT_BODY,
    FS_SM,
    FS_SM2,
    FS_MD,
    FW_MEDIUM,
    FW_BOLD,
    SP_1,
    SP_2,
    SP_3,
    SP_4,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_XL,
)

# Pixel constants
_TOAST_WIDTH: int = 320
_TOAST_MARGIN_RIGHT: int = 16
_TOAST_MARGIN_BOTTOM: int = 16
_TOAST_GAP: int = 8

# Duration constants
_AUTO_DISMISS_MS: int = 4000
_SLIDE_DURATION_MS: int = 280

# Kind → (bg, fg, accent, icon)
_KIND_STYLE: dict[str, tuple[str, str, str, str]] = {
    "info":    ("#FFFFFF",     "#142430", "#104063", "ℹ"),
    "success": ("#FFFFFF",     "#142430", "#3F6E55", "✓"),
    "warning": ("#FFFFFF",     "#142430", "#B58A3F", "⚠"),
    "error":   ("#FFFFFF",     "#142430", "#9A3B3B", "✕"),
}


class Toast(QFrame):
    """Self-dismissing toast notification.

    The toast slides in from the bottom-right of its *parent* window and
    dismisses itself after :pydata:`_AUTO_DISMISS_MS` milliseconds (or when
    the user clicks the close button).

    Parameters
    ----------
    message:
        Text to display in the toast body.
    kind:
        One of ``"info"``, ``"success"``, ``"warning"``, ``"error"``.
    parent:
        Must be the main window (or any widget that fills the screen), so
        that absolute positioning works correctly.
    """

    def __init__(
        self,
        message: str,
        kind: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind if kind in _KIND_STYLE else "info"
        bg, fg, accent, icon = _KIND_STYLE[self._kind]

        self.setObjectName("Toast")
        self.setFixedWidth(_TOAST_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.setStyleSheet(
            f"""
            QFrame#Toast {{
                background-color: {bg};
                border: 1px solid rgba(20,36,48,0.12);
                border-left: 3px solid {accent};
                border-radius: {RADIUS_LG}px;
            }}
            """
        )
        # Drop shadow via graphic effect would require QGraphicsDropShadowEffect;
        # we use a subtle border instead to keep it lightweight.

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SP_3, SP_2, SP_2, SP_2)
        layout.setSpacing(SP_2)

        # Icon
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"color: {accent}; font-size: {FS_MD}px; background: transparent; border: none; font-weight: {FW_BOLD};"
        )
        icon_lbl.setFixedWidth(18)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(icon_lbl)

        # Message
        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(msg_lbl, stretch=1)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                color: rgba(20,36,48,0.50);
                font-size: 16px;
                background: transparent;
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 0;
            }}
            QPushButton:hover {{
                color: rgba(20,36,48,0.80);
                background-color: rgba(20,36,48,0.06);
            }}
            """
        )
        close_btn.clicked.connect(self._dismiss)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)

        self.adjustSize()

        # Auto-dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_AUTO_DISMISS_MS)
        self._timer.timeout.connect(self._dismiss)

        # Slide-in animation
        self._anim: QPropertyAnimation | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def slide_in(self, final_pos: QPoint) -> None:
        """Animate the toast sliding up from below *final_pos*."""
        start_pos = QPoint(final_pos.x(), final_pos.y() + 60)
        self.move(start_pos)
        self.show()

        self._anim = QPropertyAnimation(self, QByteArray(b"pos"), self)
        self._anim.setDuration(_SLIDE_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(start_pos)
        self._anim.setEndValue(final_pos)
        self._anim.start()

        self._timer.start()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _dismiss(self) -> None:
        """Slide out and delete the widget."""
        self._timer.stop()
        if self._anim is not None:
            self._anim.stop()

        current_pos = self.pos()
        end_pos = QPoint(current_pos.x(), current_pos.y() + 60)

        out_anim = QPropertyAnimation(self, QByteArray(b"pos"), self)
        out_anim.setDuration(_SLIDE_DURATION_MS)
        out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        out_anim.setStartValue(current_pos)
        out_anim.setEndValue(end_pos)
        out_anim.finished.connect(self.deleteLater)
        out_anim.start()
        self._anim = out_anim



class ToastManager:
    """Create and stack multiple toasts anchored to the bottom-right of *parent*.

    Usage::

        mgr = ToastManager(main_window)
        mgr.push("Salvo com sucesso!", kind="success")
        mgr.push("Erro ao conectar", kind="error")
    """

    def __init__(self, parent: QWidget) -> None:
        self._parent = parent
        self._stack: list[Toast] = []

    def push(self, message: str, kind: str = "info") -> None:
        """Show a new toast and stack it above existing ones."""
        # Purge any toasts that have already been dismissed (deleted)
        self._stack = [t for t in self._stack if t.parent() is not None]

        toast = Toast(message, kind, parent=self._parent)
        toast.adjustSize()

        # Connect deletion to re-layout remaining toasts
        toast.destroyed.connect(self._on_toast_destroyed)

        self._stack.append(toast)
        self._reposition_all()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_toast_destroyed(self) -> None:
        self._stack = [t for t in self._stack if t.parent() is not None]
        self._reposition_all()

    def _reposition_all(self) -> None:
        """Recalculate positions for all live toasts from bottom up."""
        if not self._parent:
            return

        pw = self._parent.width()
        ph = self._parent.height()

        bottom_y = ph - _TOAST_MARGIN_BOTTOM
        for toast in reversed(self._stack):
            if toast.parent() is None:
                continue
            toast.adjustSize()
            th = toast.height()
            x = pw - _TOAST_WIDTH - _TOAST_MARGIN_RIGHT
            y = bottom_y - th
            final_pos = QPoint(x, y)
            toast.slide_in(final_pos)
            bottom_y = y - _TOAST_GAP
