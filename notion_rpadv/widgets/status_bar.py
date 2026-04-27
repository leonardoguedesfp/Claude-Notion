"""Bottom status bar widget."""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtWidgets import (
    QStatusBar,
    QLabel,
    QWidget,
    QHBoxLayout,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer

from notion_rpadv.theme.tokens import (
    LIGHT,
    FONT_BODY,
    FONT_MONO,
    FS_SM,
    FW_MEDIUM,
    SP_1,
    SP_3,
)

_BG_COLOR: str = "#F0EDE7"
_FG_MUTED: str = "#6F6B68"
_FG_NORMAL: str = "#3F4751"
_ACCENT: str = "#104063"
_SUCCESS: str = "#3F6E55"
_WARNING: str = "#B58A3F"


def _label(
    text: str = "",
    muted: bool = False,
    mono: bool = False,
) -> QLabel:
    """Create a pre-styled status bar label."""
    lbl = QLabel(text)
    font_fam = FONT_MONO if mono else FONT_BODY
    fg = _FG_MUTED if muted else _FG_NORMAL
    lbl.setStyleSheet(
        f"""
        QLabel {{
            color: {fg};
            font-family: "{font_fam}", "Segoe UI", Arial, sans-serif;
            font-size: {FS_SM}px;
            font-weight: {FW_MEDIUM};
            background: transparent;
            border: none;
        }}
        """
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    return lbl


def _separator() -> QFrame:
    """Thin vertical divider for use inside status bar."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Plain)
    sep.setFixedWidth(1)
    sep.setFixedHeight(14)
    sep.setStyleSheet("background-color: rgba(20,36,48,0.15); border: none;")
    return sep


class _PendingBadge(QWidget):
    """Small pill showing the number of pending (unsaved) edits."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SP_1)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {_WARNING}; font-size: {FS_SM}px; background: transparent; border: none;"
        )
        self._count_lbl = QLabel("0 pendentes")
        self._count_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {_WARNING};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(self._dot)
        layout.addWidget(self._count_lbl)
        self.setVisible(False)

    def set_count(self, n: int) -> None:
        if n <= 0:
            self.setVisible(False)
        else:
            unit = "edição" if n == 1 else "edições"
            self._count_lbl.setText(f"{n} {unit} pendentes")
            self.setVisible(True)


class AppStatusBar(QStatusBar):
    """Shows sync status, pending edit count, and last sync time.

    Layout (left to right)::

        ● synced   |  3 edições pendentes   |   Última sync: 14:32

    The right side keeps the last-sync timestamp; the centre area shows the
    pending edit count badge.  Use :meth:`show_message` for temporary text.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(
            f"""
            QStatusBar {{
                background-color: {_BG_COLOR};
                border-top: 1px solid rgba(20,36,48,0.10);
                padding: 0 {SP_3}px;
                min-height: 26px;
                max-height: 26px;
            }}
            QStatusBar::item {{
                border: none;
            }}
            """
        )

        # --- Left: sync status indicator ---
        self._sync_dot = QLabel("●")
        self._sync_dot.setStyleSheet(
            f"color: {_SUCCESS}; font-size: {FS_SM}px; background: transparent; border: none;"
        )
        self._sync_lbl = _label("Sincronizado")

        left_widget = QWidget()
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SP_1)
        left_layout.addWidget(self._sync_dot)
        left_layout.addWidget(self._sync_lbl)
        left_widget.setStyleSheet("background: transparent;")
        self.addWidget(left_widget)

        # Separator
        self.addWidget(_separator())

        # --- Centre: pending edits badge ---
        self._pending = _PendingBadge()
        self.addWidget(self._pending)

        # Push right-side widgets to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setStyleSheet("background: transparent;")
        self.addWidget(spacer)

        # --- Right: last sync timestamp ---
        self._sep_right = _separator()
        self.addPermanentWidget(self._sep_right)

        self._last_sync_lbl = _label("", muted=True)
        self.addPermanentWidget(self._last_sync_lbl)

        # Timer to auto-refresh relative timestamps (every 60 s)
        self._last_sync_ts: float = 0.0
        self._last_sync_base: str = ""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60_000)
        self._refresh_timer.timeout.connect(self._refresh_sync_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_sync_status(self, text: str) -> None:
        """Update the left-side sync text (e.g. 'Sincronizando…', 'Erro')."""
        self._sync_lbl.setText(text)
        lo = text.lower()
        if "erro" in lo or "error" in lo:
            color = LIGHT.app_danger
        elif "sincronizando" in lo or "sync" in lo or "salvando" in lo:
            # BUG-N21: 'Salvando…' should also be warning (amber dot), not success
            color = _WARNING
        else:
            color = _SUCCESS
        self._sync_dot.setStyleSheet(
            f"color: {color}; font-size: {FS_SM}px; background: transparent; border: none;"
        )

    def set_pending_count(self, n: int) -> None:
        """Show/hide the pending edits badge with count *n*."""
        self._pending.set_count(n)

    def set_last_sync(self, base: str, ts: float) -> None:
        """Set the last sync display.

        Parameters
        ----------
        base:
            Human-readable prefix such as ``"Última sync"`` or ``"Synced"``.
        ts:
            POSIX timestamp of the last successful sync.
        """
        self._last_sync_base = base
        self._last_sync_ts = ts
        self._refresh_sync_label()
        self._refresh_timer.start()

    def show_message(self, text: str, timeout_ms: int = 3000) -> None:
        """Display a temporary message in the status bar, then restore."""
        self.showMessage(text, timeout_ms)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_sync_label(self) -> None:
        """Recompute the human-friendly relative time and update the label."""
        if self._last_sync_ts <= 0:
            self._last_sync_lbl.setText("")
            self._sep_right.setVisible(False)
            return

        self._sep_right.setVisible(True)
        elapsed = time.time() - self._last_sync_ts
        if elapsed < 60:
            rel = "agora"
        elif elapsed < 3600:
            mins = int(elapsed // 60)
            rel = f"{mins} min atrás"
        else:
            dt = datetime.fromtimestamp(self._last_sync_ts)
            rel = dt.strftime("%H:%M")

        self._last_sync_lbl.setText(f"{self._last_sync_base}: {rel}")
