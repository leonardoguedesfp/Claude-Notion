"""Dashboard page — stat cards + urgent tasks list."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from notion_bulk_edit.config import DATA_SOURCES
from notion_rpadv.cache import db as cache_db
from notion_rpadv.theme.tokens import (
    DARK,
    FONT_BODY,
    FONT_DISPLAY,
    FS_MD,
    FS_SM,
    FS_SM2,
    FS_XL,
    FW_BOLD,
    FW_MEDIUM,
    LIGHT,
    Palette,
    RADIUS_MD,
    RADIUS_XL,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)

# ---------------------------------------------------------------------------
# Spacing constant that may not exist in older token sets
# ---------------------------------------------------------------------------
try:
    from notion_rpadv.theme.tokens import SP_1
except ImportError:
    SP_1 = 4  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# pt-BR month names for locale-independent date formatting
# ---------------------------------------------------------------------------
_PT_BR_MONTHS: tuple[str, ...] = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
_PT_BR_WEEKDAYS: tuple[str, ...] = (
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
)

# BUG-V2-06: cap how many urgent rows the dashboard pre-allocates. Anything
# beyond this is collapsed into a "+N mais" indicator (or simply truncated
# silently — the spec says 7-day window, in practice it's rarely >10).
_MAX_URGENT_TASKS: int = 10


def _format_date_pt_br(dt: datetime) -> str:
    """Return e.g. 'segunda-feira, 27 de abril de 2026'."""
    weekday = _PT_BR_WEEKDAYS[dt.weekday()]
    month = _PT_BR_MONTHS[dt.month - 1]
    return f"{weekday}, {dt.day} de {month} de {dt.year}"


# ---------------------------------------------------------------------------
# Stat Card
# ---------------------------------------------------------------------------

class StatCard(QFrame):
    """A single stat card: large number + descriptive label.

    Parameters
    ----------
    label:
        Caption shown below the value, e.g. "Processos Ativos".
    value:
        Numeric or textual value displayed prominently.
    color:
        Semantic accent color — "accent" | "success" | "warning" | "danger".
    label_zero:
        §2.2 Optional calm-zero text shown when value == 0 instead of "0".
    """

    def __init__(
        self,
        label: str,
        value: str | int,
        color: str = "accent",
        dark: bool = False,
        label_zero: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        p: Palette = DARK if dark else LIGHT
        self._p = p
        self._label_zero = label_zero
        # N5: remember the semantic colour key so apply_theme can re-resolve
        # the accent against the new palette without losing the choice.
        self._color_key: str = color
        self._is_zero: bool = False

        _COLOR_MAP: dict[str, str] = {
            "accent":  p.app_accent,
            "success": p.app_success,
            "warning": p.app_warning,
            "danger":  p.app_danger,
        }
        self._accent = _COLOR_MAP.get(color, p.app_accent)

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {p.app_panel};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_XL}px;
                border-left: 4px solid {self._accent};
            }}
            """
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP_4, SP_4, SP_4, SP_4)
        layout.setSpacing(SP_2)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # BUG-27: store as attribute so update_value() doesn't use fragile findChildren
        self._val_lbl = QLabel(str(value))
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        val_font = QFont(FONT_DISPLAY)
        val_font.setPixelSize(32)
        val_font.setWeight(QFont.Weight(FW_BOLD))
        self._val_lbl.setFont(val_font)
        self._val_lbl.setStyleSheet(
            f"color: {self._accent}; background: transparent; border: none;"
        )
        layout.addWidget(self._val_lbl)

        # Caption label (also stored for calm-zero label swap)
        self._cap_lbl = QLabel(label)
        self._cap_label_default = label
        self._cap_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._cap_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(self._cap_lbl)

    def update_value(self, value: str | int) -> None:
        """Update the displayed value; §2.2 switches to calm-zero style when value=0."""
        self._val_lbl.setText(str(value))
        self._is_zero = str(value) in ("0", "—")
        if self._label_zero and self._is_zero:
            # §2.2 calm-zero: neutral color, lighter weight, sub-label swap
            self._val_lbl.setStyleSheet(
                f"color: {self._p.app_fg_subtle}; background: transparent; border: none;"
            )
            self._cap_lbl.setText(self._label_zero)
        else:
            self._val_lbl.setStyleSheet(
                f"color: {self._accent}; background: transparent; border: none;"
            )
            self._cap_lbl.setText(self._cap_label_default)

    def apply_theme(self, dark: bool) -> None:
        """N5: refresh palette-derived colours on theme toggle."""
        new_p: Palette = DARK if dark else LIGHT
        if new_p is self._p:
            return
        self._p = new_p
        # Recompute the accent for the current colour name, since DARK and
        # LIGHT use different shades for status colours.
        accent_map = {
            "accent":  new_p.app_accent,
            "success": new_p.app_success,
            "warning": new_p.app_warning,
            "danger":  new_p.app_danger,
        }
        # Best-effort: derive the colour name back from current accent.
        for name, c in accent_map.items():
            # Map identity is what we have — pick by ordering precedence.
            del name, c  # noqa: F841 — placeholder for future colour-key plumbing
        self._accent = accent_map.get(self._color_key, new_p.app_accent)
        # Restyle everything that depends on the palette.
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {new_p.app_panel};
                border: 1px solid {new_p.app_border};
                border-radius: {RADIUS_XL}px;
                border-left: 4px solid {self._accent};
            }}
            """
        )
        self._cap_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {new_p.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        # Re-apply the value-label style — calm-zero vs accent-coloured.
        if self._label_zero and self._is_zero:
            self._val_lbl.setStyleSheet(
                f"color: {new_p.app_fg_subtle}; background: transparent; border: none;"
            )
        else:
            self._val_lbl.setStyleSheet(
                f"color: {self._accent}; background: transparent; border: none;"
            )


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _section_heading(text: str, p: Palette) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"""
        QLabel {{
            color: {p.app_fg_strong};
            font-family: "{FONT_DISPLAY}", Georgia, serif;
            font-size: {FS_XL}px;
            font-weight: {FW_BOLD};
            background: transparent;
            border: none;
        }}
        """
    )
    return lbl


def _body_label(text: str, p: Palette, muted: bool = False, size: int = FS_MD) -> QLabel:
    lbl = QLabel(text)
    fg = p.app_fg_muted if muted else p.app_fg
    lbl.setStyleSheet(
        f"""
        QLabel {{
            color: {fg};
            font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
            font-size: {size}px;
            background: transparent;
            border: none;
        }}
        """
    )
    return lbl


# ---------------------------------------------------------------------------
# Urgent task row
# ---------------------------------------------------------------------------

class _SyncRow(QFrame):
    """§2.3: 5-column row for the Dashboard sync panel.

    Columns (left to right):
      1. base name
      2. counter "<done>/<total>" (or "1108" idle, "—" never synced)
      3. progress bar (visible only while syncing — determinate when total
         is known)
      4. timestamp ("há 5 min" / "27/04 14:32" / "—")
      5. status chip ("OK" / "Sincronizando…" / "Erro" / "Pendente")

    The widgets are persistent — :meth:`set_state_idle` /
    :meth:`set_state_syncing` / :meth:`set_state_error` /
    :meth:`set_state_pending` mutate text/colour without churn.
    """

    # State enum (kept as strings for cheap comparisons / debugging).
    STATE_IDLE = "idle"
    STATE_SYNCING = "syncing"
    STATE_ERROR = "error"
    STATE_PENDING = "pending"

    def __init__(self, base: str, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base = base
        self._p = p
        self._state = self.STATE_PENDING
        self._total = 0
        self._current = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SP_3)

        self.dot = QLabel("●")
        self.dot.setFixedWidth(12)
        layout.addWidget(self.dot)

        # 1. Base name
        self._name_lbl = QLabel(base)
        self._name_lbl.setFixedWidth(120)
        layout.addWidget(self._name_lbl)

        # 2. Count
        self._count_lbl = QLabel("—")
        self._count_lbl.setFixedWidth(96)
        self._count_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self._count_lbl)

        # 3. Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedHeight(4)
        self._progress.setMaximumWidth(220)
        self._progress.setMinimumWidth(140)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress, stretch=1)

        # 4. Timestamp
        self.when_lbl = QLabel("nunca sincronizado")
        self.when_lbl.setMinimumWidth(140)
        layout.addWidget(self.when_lbl)

        # 5. Chip
        self._chip = QLabel("Pendente")
        self._chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chip.setFixedWidth(110)
        self._chip.setFixedHeight(20)
        layout.addWidget(self._chip)

        self._restyle()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def set_state_idle(self, total: int, when_text: str) -> None:
        self._state = self.STATE_IDLE
        self._total = total
        self._current = total
        self._count_lbl.setText(f"{total:n}".replace(",", ".") if total > 0 else "—")
        self._progress.setVisible(False)
        self.when_lbl.setText(when_text)
        self._chip.setText("OK")
        self._restyle()

    def set_state_pending(self) -> None:
        self._state = self.STATE_PENDING
        self._total = 0
        self._current = 0
        self._count_lbl.setText("—")
        self._progress.setVisible(False)
        self.when_lbl.setText("nunca sincronizado")
        self._chip.setText("Pendente")
        self._restyle()

    def set_state_syncing(self, current: int = 0, total: int = 0) -> None:
        self._state = self.STATE_SYNCING
        self._current = current
        self._total = total
        self._progress.setVisible(True)
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(current)
            self._count_lbl.setText(f"{current}/{total}")
        else:
            # Indeterminate until SyncWorker.total arrives
            self._progress.setRange(0, 0)
            self._count_lbl.setText("…")
        self.when_lbl.setText("agora")
        self._chip.setText("Sincronizando…")
        self._restyle()

    def set_state_error(self, when_text: str = "—") -> None:
        self._state = self.STATE_ERROR
        self._progress.setVisible(False)
        self.when_lbl.setText(when_text)
        self._chip.setText("Erro")
        self._restyle()

    def set_progress(self, current: int) -> None:
        if self._state != self.STATE_SYNCING:
            return
        self._current = current
        if self._total > 0:
            self._progress.setValue(current)
            self._count_lbl.setText(f"{current}/{self._total}")

    def set_total(self, total: int) -> None:
        self._total = total
        if self._state == self.STATE_SYNCING:
            self._progress.setRange(0, total)
            self._progress.setValue(self._current)
            self._count_lbl.setText(f"{self._current}/{total}")

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def apply_theme(self, dark: bool) -> None:
        self._p = DARK if dark else LIGHT
        self._restyle()

    def _restyle(self) -> None:
        p = self._p
        # Dot colour by state
        dot_color = {
            self.STATE_IDLE:    p.app_success,
            self.STATE_SYNCING: p.app_warning,
            self.STATE_ERROR:   p.app_danger,
            self.STATE_PENDING: p.app_fg_subtle,
        }.get(self._state, p.app_fg_subtle)
        self.dot.setStyleSheet(
            f"color: {dot_color}; font-size: 10px; background: transparent; border: none;"
        )

        body_lbl_css = (
            f"QLabel {{"
            f" color: {p.app_fg_muted};"
            f" font-family: '{FONT_BODY}', 'Segoe UI', Arial, sans-serif;"
            f" font-size: {FS_SM2}px;"
            f" background: transparent; border: none; }}"
        )
        self._name_lbl.setStyleSheet(
            f"QLabel {{ color: {p.app_fg}; font-family: '{FONT_BODY}', 'Segoe UI', Arial, sans-serif;"
            f" font-size: {FS_SM2}px; font-weight: {FW_MEDIUM};"
            f" background: transparent; border: none; }}"
        )
        self._count_lbl.setStyleSheet(body_lbl_css)
        self.when_lbl.setStyleSheet(body_lbl_css)

        # Progress bar tint
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {p.app_border};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {p.app_accent};
                border-radius: 2px;
            }}
            """
        )

        # Chip palette per state
        if self._state == self.STATE_IDLE:
            chip_bg, chip_fg = p.app_success_bg, p.app_success
        elif self._state == self.STATE_SYNCING:
            chip_bg, chip_fg = p.app_warning_bg, p.app_warning
        elif self._state == self.STATE_ERROR:
            chip_bg, chip_fg = p.app_danger_bg, p.app_danger
        else:
            chip_bg, chip_fg = p.app_row_hover, p.app_fg_subtle
        self._chip.setStyleSheet(
            f"""
            QLabel {{
                color: {chip_fg};
                background-color: {chip_bg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_BOLD};
                letter-spacing: 0.04em;
                border: none;
                border-radius: 10px;
                padding: 0 8px;
            }}
            """
        )


class _TaskRow(QFrame):
    """Single row in the urgent tasks list. Reusable: build once, ``update()``
    it on every refresh instead of creating a new instance — keeps the pool
    of widgets bounded and the dashboard refresh idempotent."""

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {p.app_panel};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
            }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SP_3, SP_2, SP_3, SP_2)
        layout.setSpacing(SP_3)

        # Task title — always present.
        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_fg_strong};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(self._title_lbl, stretch=2)

        # Process number — always created; hidden when empty.
        self._proc_lbl = QLabel("")
        self._proc_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(self._proc_lbl, stretch=1)

        # Days badge — fixed position; restyled per update.
        self._badge = QLabel("")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedSize(52, 22)
        layout.addWidget(self._badge)

    def apply_theme(self, dark: bool) -> None:
        """N5: switch palette on theme toggle. Title/processo/days are
        re-derived on the next ``update_row()`` call from cached state."""
        new_p: Palette = DARK if dark else LIGHT
        if new_p is self._p:
            return
        self._p = new_p
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {new_p.app_panel};
                border: 1px solid {new_p.app_border};
                border-radius: {RADIUS_MD}px;
            }}
            """
        )
        self._title_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {new_p.app_fg_strong};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        self._proc_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {new_p.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                background: transparent;
                border: none;
            }}
            """
        )
        # Re-apply the badge style by walking the cached badge text/days.
        # Since update_row() parses days_left to text, we re-derive from
        # the badge's current text (e.g. "VENCIDO", "3d") when possible.

    def update_row(self, title: str, processo: str, days_left: int) -> None:
        """Repoint this row at a new (title, processo, days_left) tuple."""
        p = self._p
        self._title_lbl.setText(title or "(sem título)")
        if processo:
            self._proc_lbl.setText(processo)
            self._proc_lbl.setVisible(True)
        else:
            self._proc_lbl.setText("")
            self._proc_lbl.setVisible(False)

        if days_left <= 0:
            badge_text = "VENCIDO"
            badge_bg = p.app_danger_bg
            badge_fg = p.app_danger
        elif days_left <= 2:
            badge_text = f"{days_left}d"
            badge_bg = p.app_danger_bg
            badge_fg = p.app_danger
        elif days_left <= 5:
            badge_text = f"{days_left}d"
            badge_bg = p.app_warning_bg
            badge_fg = p.app_warning
        else:
            badge_text = f"{days_left}d"
            badge_bg = p.app_success_bg
            badge_fg = p.app_success

        self._badge.setText(badge_text)
        self._badge.setStyleSheet(
            f"""
            QLabel {{
                color: {badge_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_BOLD};
                background-color: {badge_bg};
                border-radius: 11px;
                border: none;
                padding: 0 6px;
            }}
            """
        )


# ---------------------------------------------------------------------------
# Main DashboardPage
# ---------------------------------------------------------------------------

class DashboardPage(QWidget):
    """Dashboard showing firm-wide statistics, urgent tasks, and sync status."""

    sync_requested: Signal = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        user: dict[str, str],
        dark: bool = False,
        sync_manager: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._dark = dark
        self._p: Palette = DARK if dark else LIGHT
        self._sync_manager = sync_manager
        # §2.3: bases that are currently syncing — used to show/hide the
        # global progress strip in the toolbar.
        self._active_syncs: set[str] = set()
        # §2.3 / FALHA-4: explicit "should the strip be visible right now?"
        # flag. Mirrors the active_syncs predicate but is independent of
        # Qt's ancestor-aware ``isVisible()`` so tests can assert on intent.
        self._global_progress_visible: bool = False

        self._build_ui()

        # §2.3: subscribe to live sync signals so the panel paints progress
        # without polling. The signals are forwarded by SyncManager from the
        # underlying SyncWorker.
        if sync_manager is not None:
            for signal_name, slot in (
                ("base_started", self._on_base_started),
                ("base_total", self._on_base_total),
                ("base_progress", self._on_base_progress),
                ("base_done", self._on_base_done_for_panel),
                ("sync_error", self._on_sync_error_for_panel),
            ):
                sig = getattr(sync_manager, signal_name, None)
                if sig is not None:
                    try:
                        sig.connect(slot)
                    except (TypeError, AttributeError):
                        pass

        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Recompute all stats from the SQLite cache and update the UI."""
        self._load_stats()
        self._load_urgent_tasks()
        self._load_sync_status()

    def apply_theme(self, dark: bool) -> None:
        """N5: propagate the theme switch to every palette-aware child."""
        if dark == self._dark:
            return
        self._dark = dark
        self._p = DARK if dark else LIGHT
        # Cards
        for card in (
            getattr(self, "_card_processos", None),
            getattr(self, "_card_tarefas", None),
            getattr(self, "_card_criticos", None),
            getattr(self, "_card_clientes", None),
        ):
            if card is not None and hasattr(card, "apply_theme"):
                card.apply_theme(dark)
        # Urgent task rows
        for row in getattr(self, "_urgent_rows", []):
            if hasattr(row, "apply_theme"):
                row.apply_theme(dark)
        # Sync rows
        for srow in getattr(self, "_sync_rows", {}).values():
            if hasattr(srow, "apply_theme"):
                srow.apply_theme(dark)
        # Global progress strip — re-style.
        self._restyle_global_progress()
        # Re-run refresh: persistent labels just get text/colour updates,
        # which is the cheapest way to flush the new palette through.
        self.refresh()

    # ------------------------------------------------------------------
    # §2.3 Live sync signals
    # ------------------------------------------------------------------

    def _on_base_started(self, base: str) -> None:
        srow = self._sync_rows.get(base)
        if srow is not None:
            srow.set_state_syncing(0, 0)
        self._active_syncs.add(base)
        self._show_global_progress(True)

    def _on_base_total(self, base: str, total: int) -> None:
        srow = self._sync_rows.get(base)
        if srow is not None:
            srow.set_total(total)

    def _on_base_progress(self, base: str, current: int) -> None:
        srow = self._sync_rows.get(base)
        if srow is not None:
            srow.set_progress(current)

    def _on_base_done_for_panel(
        self, base: str, _added: int, existing: int, _removed: int
    ) -> None:
        # Total visible rows = added + existing (new + already-present).
        # We don't have access to "added" alone here without including it,
        # but the simplest accurate display is: read the cache size now.
        try:
            total = len(cache_db.get_all_records(self._conn, base))
        except Exception:  # noqa: BLE001
            total = existing
        try:
            ts = cache_db.get_last_sync(self._conn, base)
        except Exception:  # noqa: BLE001
            ts = 0.0
        when_text = self._format_when(ts)
        srow = self._sync_rows.get(base)
        if srow is not None:
            srow.set_state_idle(total, when_text)
        self._active_syncs.discard(base)
        if not self._active_syncs:
            self._show_global_progress(False)

    def _on_sync_error_for_panel(self, base: str, _msg: str) -> None:
        srow = self._sync_rows.get(base)
        if srow is not None:
            srow.set_state_error()
        self._active_syncs.discard(base)
        if not self._active_syncs:
            self._show_global_progress(False)

    # ------------------------------------------------------------------
    # §2.3 Global progress strip
    # ------------------------------------------------------------------

    def _show_global_progress(self, on: bool) -> None:
        """§2.3: drive the global progress strip from the live sync state.

        Sets both the widget's visibility AND a plain bool flag the test
        suite (and any future dev tooling) can assert against. The flag is
        useful because Qt's ``isVisible()`` returns False whenever any
        ancestor is hidden — meaning a widget whose ``setVisible(True)``
        was called legitimately can still report False in unit tests
        where the widget tree was never shown. ``_global_progress_visible``
        captures the *intent* unambiguously.
        """
        self._global_progress_visible: bool = bool(on)
        if hasattr(self, "_global_progress"):
            # Use show()/hide() instead of setVisible() so behaviour is
            # symmetric with what production code does and so the
            # WA_WState_Hidden flag flips deterministically.
            if on:
                self._global_progress.show()
            else:
                self._global_progress.hide()

    def _restyle_global_progress(self) -> None:
        if not hasattr(self, "_global_progress"):
            return
        p = self._p
        self._global_progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: transparent;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {p.app_accent};
            }}
            """
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Toolbar (pinned above scroll area) ----
        toolbar = self._build_toolbar(self._user)
        outer.addWidget(toolbar)

        # §2.3: 2px global progress strip — sits flush under the toolbar,
        # visible only while at least one base is syncing.
        self._global_progress = QProgressBar()
        self._global_progress.setFixedHeight(2)
        self._global_progress.setRange(0, 0)  # indeterminate
        self._global_progress.setTextVisible(False)
        self._global_progress.setVisible(False)
        outer.addWidget(self._global_progress)
        self._restyle_global_progress()

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet(f"background-color: {p.app_bg};")
        scroll.setWidget(content)

        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(SP_8, SP_6, SP_8, SP_8)
        self._content_layout.setSpacing(SP_8)  # §2.1 32px between sections

        # ---- Stat cards row ----
        cards_row = QHBoxLayout()
        cards_row.setSpacing(SP_4)
        self._card_processos = StatCard("Processos Ativos", "—", "accent", self._dark)
        # §2.2 calm-zero: neutral style when count is 0
        self._card_tarefas   = StatCard("Tarefas Hoje", "—", "warning", self._dark, label_zero="Sem tarefas hoje")
        self._card_criticos  = StatCard("Prazo Crítico", "—", "danger", self._dark, label_zero="Nenhum prazo crítico")
        self._card_clientes  = StatCard("Clientes", "—", "success", self._dark)
        for card in (
            self._card_processos,
            self._card_tarefas,
            self._card_criticos,
            self._card_clientes,
        ):
            cards_row.addWidget(card)
        self._content_layout.addLayout(cards_row)

        # ---- Urgent tasks ----
        # BUG-V2-06: same persistent-widget approach as the sync panel.
        # Pre-allocate a fixed pool of _TaskRow widgets (matching the cap
        # in _load_urgent_tasks) plus an "empty" placeholder label, then
        # only toggle visibility / mutate text on each refresh. No widget
        # churn, no DeferredDelete dependence.
        self._content_layout.addWidget(_section_heading("Tarefas Urgentes", p))
        self._tasks_container = QVBoxLayout()
        self._tasks_container.setSpacing(SP_2)
        self._content_layout.addLayout(self._tasks_container)

        self._urgent_rows: list[_TaskRow] = []
        for _ in range(_MAX_URGENT_TASKS):
            row = _TaskRow(p)
            row.setVisible(False)
            self._tasks_container.addWidget(row)
            self._urgent_rows.append(row)
        self._urgent_empty_lbl = _body_label(
            "Nenhuma tarefa urgente nos próximos 7 dias.", p, muted=True
        )
        self._urgent_empty_lbl.setVisible(False)
        self._tasks_container.addWidget(self._urgent_empty_lbl)
        # Sentinel for "could not load tasks" — surfaced from cache errors.
        self._urgent_error_lbl = _body_label("", p, muted=True)
        self._urgent_error_lbl.setVisible(False)
        self._tasks_container.addWidget(self._urgent_error_lbl)

        # ---- Sync status — §2.3: 5-column layout per base ----
        # Columns: name | count | progress bar | timestamp | chip
        # All widgets are persistent: refresh() and live sync events only
        # mutate text/value/colour. Idempotent across any number of refreshes.
        self._content_layout.addWidget(_section_heading("Sincronização", p))
        self._sync_container = QVBoxLayout()
        self._sync_container.setSpacing(SP_2)
        self._content_layout.addLayout(self._sync_container)

        self._sync_rows: dict[str, _SyncRow] = {}
        for base in DATA_SOURCES:
            srow = _SyncRow(base, p)
            self._sync_container.addWidget(srow)
            self._sync_rows[base] = srow

        # §2.3 also keeps backward-compatible dict aliases so external code
        # (and the old test labels) can still locate the per-base text label.
        self._sync_lbls: dict[str, QLabel] = {
            b: r.when_lbl for b, r in self._sync_rows.items()
        }
        self._sync_dots: dict[str, QLabel] = {
            b: r.dot for b, r in self._sync_rows.items()
        }

        self._content_layout.addStretch()

    def _build_toolbar(self, user: dict[str, str]) -> QFrame:
        """Build the dashboard toolbar QFrame matching the HTML prototype spec."""
        p = self._p
        now = datetime.now()

        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        toolbar.setStyleSheet(
            f"""
            QFrame#Toolbar {{
                background-color: {p.app_bg};
                border-bottom: 1px solid {p.app_border};
            }}
            """
        )

        row = QHBoxLayout(toolbar)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(10)

        # 1. Greeting title: "Bom dia, Nome."
        greeting_text = self._get_greeting(user.get("name", ""))
        greeting_lbl = QLabel(greeting_text)
        greeting_lbl.setObjectName("ToolbarTitle")
        title_font = QFont(FONT_DISPLAY)
        title_font.setPixelSize(22)
        title_font.setWeight(QFont.Weight(400))
        greeting_lbl.setFont(title_font)
        greeting_lbl.setStyleSheet(
            f"""
            QLabel#ToolbarTitle {{
                font-family: "{FONT_DISPLAY}", "Cormorant Garamond", Georgia, serif;
                font-size: 22px;
                font-weight: 400;
                color: {p.app_fg_strong};
                background: transparent;
                border: none;
                margin-right: 14px;
            }}
            """
        )
        row.addWidget(greeting_lbl)

        # 2. Date meta label: "segunda-feira, 27 de abril de 2026"
        date_text = _format_date_pt_br(now)
        date_lbl = QLabel(date_text)
        date_lbl.setObjectName("ToolbarMeta")
        date_lbl.setStyleSheet(
            f"""
            QLabel#ToolbarMeta {{
                font-size: 11px;
                color: {p.app_fg_subtle};
                letter-spacing: 0.04em;
                text-transform: uppercase;
                font-weight: 600;
                background: transparent;
                border: none;
                margin-left: 12px;
                margin-right: 4px;
            }}
            """
        )
        row.addWidget(date_lbl)

        # 3. Spacer
        row.addStretch()

        # 4. "Última sync: …" label
        self._last_sync_lbl = QLabel("Última sync: —")
        self._last_sync_lbl.setStyleSheet(
            f"""
            QLabel {{
                font-size: 11px;
                color: {p.app_fg_subtle};
                background: transparent;
                border: none;
                margin-right: 8px;
            }}
            """
        )
        row.addWidget(self._last_sync_lbl)

        # 5. "Sincronizar tudo" button
        sync_all_btn = QPushButton("Sincronizar tudo")
        sync_all_btn.setObjectName("BtnSecondary")
        sync_all_btn.setFixedHeight(32)
        sync_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_all_btn.setStyleSheet(
            f"""
            QPushButton#BtnSecondary {{
                background-color: transparent;
                color: {p.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QPushButton#BtnSecondary:hover {{
                background-color: {p.app_row_hover};
                border-color: {p.app_border_strong};
            }}
            QPushButton#BtnSecondary:pressed {{
                background-color: {p.app_accent_soft};
            }}
            QPushButton#BtnSecondary:disabled {{
                color: {p.app_fg_subtle};
            }}
            """
        )
        sync_all_btn.clicked.connect(self.sync_requested)
        row.addWidget(sync_all_btn)

        return toolbar

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_stats(self) -> None:
        try:
            processos = cache_db.get_all_records(self._conn, "Processos")
            clientes  = cache_db.get_all_records(self._conn, "Clientes")
            tarefas   = cache_db.get_all_records(self._conn, "Tarefas")
        except Exception:  # noqa: BLE001
            return

        active_proc = sum(
            1 for r in processos
            if str(r.get("status", "")).lower() in ("ativo", "active", "")
        )
        total_clientes = len(clientes)

        today_str = date.today().isoformat()
        tarefas_hoje = sum(
            1 for r in tarefas
            if str(r.get("prazo", "") or "").startswith(today_str)
        )
        criticos = sum(
            1 for r in tarefas
            if self._days_remaining(str(r.get("prazo_fatal", "") or "")) is not None
            and (self._days_remaining(str(r.get("prazo_fatal", "") or "")) or 999) <= 3
        )

        # BUG-V1: use update_value() which targets the stored _val_lbl attribute
        self._card_processos.update_value(str(active_proc))
        self._card_tarefas.update_value(str(tarefas_hoje))
        self._card_criticos.update_value(str(criticos))
        self._card_clientes.update_value(str(total_clientes))

        # Update last-sync label from the most recent sync across all bases
        self._update_last_sync_label()

    def _update_last_sync_label(self) -> None:
        """Set the 'Última sync' label to the most recent sync timestamp."""
        latest: float = 0.0
        for base in DATA_SOURCES:
            try:
                ts = cache_db.get_last_sync(self._conn, base)
                if ts > latest:
                    latest = ts
            except Exception:  # noqa: BLE001
                pass

        if latest > 0:
            dt = datetime.fromtimestamp(latest)
            text = f"Última sync: {dt.strftime('%d/%m %H:%M')}"
        else:
            text = "Última sync: —"

        if hasattr(self, "_last_sync_lbl"):
            self._last_sync_lbl.setText(text)

    def _load_urgent_tasks(self) -> None:
        # BUG-V2-06: refresh by mutating the persistent _TaskRow pool built
        # in _build_ui — toggle visibility, never create widgets here.
        try:
            tarefas = cache_db.get_all_records(self._conn, "Tarefas")
        except Exception:  # noqa: BLE001
            self._show_urgent_error("Erro ao carregar tarefas.")
            return

        urgent: list[tuple[int, dict[str, Any]]] = []
        for r in tarefas:
            prazo_str = str(r.get("prazo_fatal", "") or r.get("prazo", "") or "")
            days = self._days_remaining(prazo_str)
            if days is not None and days <= 7:
                urgent.append((days, r))
        urgent.sort(key=lambda x: x[0])

        # Hide the error label whenever we got here without raising.
        self._urgent_error_lbl.setVisible(False)

        if not urgent:
            for row in self._urgent_rows:
                row.setVisible(False)
            self._urgent_empty_lbl.setVisible(True)
            return

        self._urgent_empty_lbl.setVisible(False)
        capped = urgent[:_MAX_URGENT_TASKS]
        for i, row in enumerate(self._urgent_rows):
            if i < len(capped):
                days, record = capped[i]
                # Fase 2d: title slug de Processos virou "numero_do_processo"
                # (era "cnj"). Mantemos fallbacks legados para records pré-2d
                # no cache até decay natural via re-sync.
                title = str(
                    record.get("tarefa")              # Tarefas (slug dinâmico)
                    or record.get("titulo")           # legacy / outras bases
                    or record.get("title")            # caminho defensivo
                    or record.get("numero_do_processo")  # Processos (Fase 2d)
                    or record.get("cnj")              # Processos legacy
                    or "",
                )
                processo = str(
                    record.get("processo")            # Tarefas → Processo (relation)
                    or record.get("numero_do_processo")  # Processos (Fase 2d)
                    or record.get("cnj")              # Processos legacy
                    or "",
                )
                row.update_row(title, processo, days)
                row.setVisible(True)
            else:
                row.setVisible(False)

    def _show_urgent_error(self, msg: str) -> None:
        """Surface a one-line error in the urgent-tasks panel."""
        for row in self._urgent_rows:
            row.setVisible(False)
        self._urgent_empty_lbl.setVisible(False)
        self._urgent_error_lbl.setText(msg)
        self._urgent_error_lbl.setVisible(True)

    def _load_sync_status(self) -> None:
        # §2.3: idle refresh — populate every persistent _SyncRow with the
        # most recent timestamp + total. Live progress is driven by the
        # SyncManager signals connected in __init__.
        for base in DATA_SOURCES:
            srow = self._sync_rows.get(base)
            if srow is None:
                continue
            # Skip the row if it's currently syncing — the live signals own
            # its state until base_done arrives.
            if srow._state == _SyncRow.STATE_SYNCING:
                continue
            try:
                ts = cache_db.get_last_sync(self._conn, base)
            except Exception:  # noqa: BLE001
                ts = 0.0
            try:
                total = len(cache_db.get_all_records(self._conn, base))
            except Exception:  # noqa: BLE001
                total = 0
            if ts > 0:
                srow.set_state_idle(total, self._format_when(ts))
            else:
                srow.set_state_pending()

    @staticmethod
    def _format_when(ts: float) -> str:
        """§2.3: human-friendly relative time for the timestamp column."""
        if ts <= 0:
            return "—"
        elapsed = datetime.now().timestamp() - ts
        if elapsed < 60:
            return "agora há pouco"
        if elapsed < 3600:
            return f"há {int(elapsed // 60)} min"
        if elapsed < 86_400:
            return f"há {int(elapsed // 3600)} h"
        return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_greeting(name: str) -> str:
        hour = datetime.now().hour
        if hour < 12:
            period = "Bom dia"
        elif hour < 18:
            period = "Boa tarde"
        else:
            period = "Boa noite"
        suffix = f", {name}." if name else "."
        return f"{period}{suffix}"

    @staticmethod
    def _days_remaining(date_str: str) -> int | None:
        if not date_str or len(date_str) < 10:
            return None
        try:
            target = date.fromisoformat(date_str[:10])
            delta = (target - date.today()).days
            return delta
        except ValueError:
            return None
