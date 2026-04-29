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
    Palette,
    SP_1,
    SP_3,
)


def _build_label(text: str, mono: bool = False) -> QLabel:
    """Create a status-bar label whose colour is set later via apply_theme()."""
    lbl = QLabel(text)
    font_fam = FONT_MONO if mono else FONT_BODY
    lbl.setProperty("_mono", mono)
    lbl.setProperty("_muted", False)
    # Style without colour — colour comes from _restyle_label() once the
    # palette is known.
    lbl.setStyleSheet(
        f"""
        QLabel {{
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


class _PendingBadge(QWidget):
    """Small pill showing the number of pending (unsaved) edits."""

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SP_1)

        self._dot = QLabel("●")
        self._count_lbl = QLabel("0 pendentes")
        layout.addWidget(self._dot)
        layout.addWidget(self._count_lbl)
        self.setVisible(False)
        self._restyle()

    def set_count(self, n: int) -> None:
        if n <= 0:
            self.setVisible(False)
        else:
            unit = "edição" if n == 1 else "edições"
            self._count_lbl.setText(f"{n} {unit} pendentes")
            self.setVisible(True)

    def apply_theme(self, p: Palette) -> None:
        """N5: refresh palette-derived colours when the active theme flips."""
        self._p = p
        self._restyle()

    def _restyle(self) -> None:
        p = self._p
        self._dot.setStyleSheet(
            f"color: {p.app_warning}; font-size: {FS_SM}px; "
            f"background: transparent; border: none;"
        )
        self._count_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_warning};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )


class AppStatusBar(QStatusBar):
    """Shows sync status, pending edit count, and last sync time.

    Layout (left to right)::

        ● synced   |  3 edições pendentes   |   Última sync: 14:32

    The right side keeps the last-sync timestamp; the centre area shows the
    pending edit count badge.  Use :meth:`show_message` for temporary text.

    N5: every colour value is derived from a :class:`Palette`; call
    :meth:`apply_theme` when the active palette changes.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        # Round 3a: kwarg dark removido — paleta única LIGHT.
        super().__init__(parent)
        self._p: Palette = LIGHT
        self.setSizeGripEnabled(False)

        # --- Left: sync status indicator ---
        self._sync_dot = QLabel("●")
        self._sync_lbl = _build_label("Sincronizado")

        self._left_widget = QWidget()
        left_layout = QHBoxLayout(self._left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SP_1)
        left_layout.addWidget(self._sync_dot)
        left_layout.addWidget(self._sync_lbl)
        self._left_widget.setStyleSheet("background: transparent;")
        self.addWidget(self._left_widget)

        # Separator
        self._sep_left = self._make_separator()
        self.addWidget(self._sep_left)

        # --- Centre: pending edits badge ---
        self._pending = _PendingBadge(self._p)
        self.addWidget(self._pending)

        # Push right-side widgets to the right
        self._spacer = QWidget()
        self._spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._spacer.setStyleSheet("background: transparent;")
        self.addWidget(self._spacer)

        # --- Right: last sync timestamp ---
        self._sep_right = self._make_separator()
        self.addPermanentWidget(self._sep_right)

        self._last_sync_lbl = _build_label("")
        self._last_sync_lbl.setProperty("_muted", True)
        # BUG-V2-11: reserve room for "Última sync: 99 min atrás" so the
        # permanent-widget area never squeezes it down to "12 min at...".
        self._last_sync_lbl.setMinimumWidth(
            self._last_sync_lbl.fontMetrics().horizontalAdvance(
                "Última sync: 99 min atrás"
            ) + 16
        )
        self.addPermanentWidget(self._last_sync_lbl)

        # Timer to auto-refresh relative timestamps (every 60 s)
        self._last_sync_ts: float = 0.0
        self._last_sync_base: str = ""
        self._sync_status_text: str = "Sincronizado"
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60_000)
        self._refresh_timer.timeout.connect(self._refresh_sync_label)

        self._restyle()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Round 3a: apply_theme removido — paleta única LIGHT.

    def set_sync_status(self, text: str) -> None:
        """Update the left-side sync text (e.g. 'Sincronizando…', 'Erro')."""
        self._sync_status_text = text
        self._sync_lbl.setText(text)
        self._restyle_sync_dot()

    def set_pending_count(self, n: int) -> None:
        """Show/hide the pending edits badge with count *n*."""
        self._pending.set_count(n)

    def set_last_sync(self, base: str, ts: float) -> None:
        """Set the last sync display."""
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

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedWidth(1)
        sep.setFixedHeight(14)
        # Colour is set in _restyle().
        return sep

    def _restyle(self) -> None:
        """N5: rebuild every inline stylesheet from the active palette."""
        p = self._p
        # Container
        self.setStyleSheet(
            f"""
            QStatusBar {{
                background-color: {p.app_panel};
                border-top: 1px solid {p.app_border};
                padding: 0 {SP_3}px;
                min-height: 26px;
                max-height: 26px;
            }}
            QStatusBar::item {{
                border: none;
            }}
            """
        )
        # Separators
        sep_style = f"background-color: {p.app_border}; border: none;"
        self._sep_left.setStyleSheet(sep_style)
        self._sep_right.setStyleSheet(sep_style)
        # Sync labels (left + right)
        for lbl in (self._sync_lbl, self._last_sync_lbl):
            self._restyle_label(lbl)
        self._restyle_sync_dot()

    def _restyle_label(self, lbl: QLabel) -> None:
        p = self._p
        muted = bool(lbl.property("_muted"))
        mono = bool(lbl.property("_mono"))
        font_fam = FONT_MONO if mono else FONT_BODY
        fg = p.app_fg_subtle if muted else p.app_fg_muted
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

    def _restyle_sync_dot(self) -> None:
        p = self._p
        lo = self._sync_status_text.lower()
        if "erro" in lo or "error" in lo:
            color = p.app_danger
        elif "sincronizando" in lo or "sync" in lo or "salvando" in lo:
            color = p.app_warning
        else:
            color = p.app_success
        self._sync_dot.setStyleSheet(
            f"color: {color}; font-size: {FS_SM}px; background: transparent; border: none;"
        )

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
