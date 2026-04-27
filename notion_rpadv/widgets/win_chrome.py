"""Custom window titlebar / chrome (optional, for frameless window)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from notion_rpadv.theme.tokens import (
    DARK,
    FS_SM2,
    FW_BOLD,
    LIGHT,
    RADIUS_MD,
    SP_2,
    SP_4,
)

# Re-export legacy aliases so existing callers that import the old signal names
# still work without changes.

_FONT_DISPLAY = "Playfair Display"


class WinChrome(QWidget):
    """Custom titlebar with minimize / maximize / close buttons.

    Designed for use with ``Qt.WindowType.FramelessWindowHint`` windows.
    Drag the bar to reposition the window; double-click to toggle maximized.

    Signals
    -------
    minimize_clicked:
        Emitted when the minimize button is clicked.
    maximize_clicked:
        Emitted when the maximize button is clicked (or the bar is double-clicked).
    close_clicked:
        Emitted when the close button is clicked.

    Backward-compatible aliases
    ---------------------------
    ``minimize_requested``, ``maximize_requested``, ``close_requested`` are
    kept as aliases for the signals above so that existing connection code
    continues to work.

    Usage::

        win = QMainWindow()
        win.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        chrome = WinChrome(title="Notion RPADV", parent=win)
        chrome.close_clicked.connect(win.close)
        chrome.minimize_clicked.connect(win.showMinimized)
        chrome.maximize_clicked.connect(
            lambda: win.showNormal() if win.isMaximized() else win.showMaximized()
        )
    """

    # Canonical signal names (spec)
    minimize_clicked: Signal = Signal()
    maximize_clicked: Signal = Signal()
    close_clicked: Signal = Signal()

    # Legacy aliases so callers using the old names still compile
    minimize_requested: Signal = Signal()
    maximize_requested: Signal = Signal()
    close_requested: Signal = Signal()

    def __init__(
        self,
        title: str = "Notion RPADV",
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark = dark
        p = DARK if dark else LIGHT
        self._drag_pos: QPoint | None = None

        self.setObjectName("WinChrome")
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"""
            QWidget#WinChrome {{
                background-color: {p.navy_dark};
                border-bottom: 1px solid rgba(237,234,228,0.10);
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SP_4, 0, SP_2, 0)
        layout.setSpacing(0)

        # Title label
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: rgba(237,234,228,0.90);
                font-family: "{_FONT_DISPLAY}", Georgia, serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_BOLD};
                background: transparent;
                border: none;
                letter-spacing: 0.5px;
            }}
            """
        )
        layout.addWidget(self._title_lbl)
        layout.addStretch()

        # Window control buttons: minimize, maximize, close
        _BTN_DEFS: list[tuple[str, str, str]] = [
            ("−", "minimize_clicked", "rgba(237,234,228,0.15)"),
            ("□", "maximize_clicked", "rgba(237,234,228,0.15)"),
            ("×", "close_clicked",    "#9A3B3B"),
        ]
        for symbol, signal_name, color_hover in _BTN_DEFS:
            btn = QPushButton(symbol)
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    color: rgba(237,234,228,0.70);
                    font-size: 14px;
                    background: transparent;
                    border: none;
                    border-radius: {RADIUS_MD}px;
                }}
                QPushButton:hover {{
                    background-color: {color_hover};
                    color: rgba(237,234,228,1.0);
                }}
                QPushButton:pressed {{
                    background-color: {color_hover};
                    opacity: 0.80;
                }}
                """
            )
            canonical_sig = getattr(self, signal_name)
            btn.clicked.connect(canonical_sig)
            # Also emit the legacy alias when the canonical signal fires
            legacy_name = signal_name.replace("_clicked", "_requested")
            legacy_sig = getattr(self, legacy_name)
            canonical_sig.connect(legacy_sig)
            layout.addWidget(btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_title(self, title: str) -> None:
        """Update the displayed window title."""
        self._title_lbl.setText(title)

    # ------------------------------------------------------------------
    # Window drag support
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            # Store global cursor position at press time
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_pos is not None
            and self.window() is not None
        ):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._drag_pos = event.globalPosition().toPoint()
            win = self.window()
            win.move(win.pos() + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """Double-clicking the titlebar toggles maximized state."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_clicked.emit()
        super().mouseDoubleClickEvent(event)
