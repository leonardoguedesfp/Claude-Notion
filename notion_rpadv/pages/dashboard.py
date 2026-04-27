"""Dashboard page — stat cards + urgent tasks list."""
from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timezone
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
    FS_LG,
    FS_MD,
    FS_SM,
    FS_SM2,
    FS_XL,
    FS_2XL,
    FW_BOLD,
    FW_MEDIUM,
    FW_REGULAR,
    LIGHT,
    Palette,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_XL,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)


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
    """

    def __init__(
        self,
        label: str,
        value: str | int,
        color: str = "accent",
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        p: Palette = DARK if dark else LIGHT

        _COLOR_MAP: dict[str, str] = {
            "accent":  p.app_accent,
            "success": p.app_success,
            "warning": p.app_warning,
            "danger":  p.app_danger,
        }
        accent = _COLOR_MAP.get(color, p.app_accent)

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {p.app_panel};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_XL}px;
                border-left: 4px solid {accent};
            }}
            """
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SP_4, SP_4, SP_4, SP_4)
        layout.setSpacing(SP_2)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Value
        val_lbl = QLabel(str(value))
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        val_font = QFont(FONT_DISPLAY)
        val_font.setPixelSize(32)
        val_font.setWeight(QFont.Weight(FW_BOLD))
        val_lbl.setFont(val_font)
        val_lbl.setStyleSheet(
            f"color: {accent}; background: transparent; border: none;"
        )
        layout.addWidget(val_lbl)

        # Label
        cap_lbl = QLabel(label)
        cap_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        cap_lbl.setStyleSheet(
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
        layout.addWidget(cap_lbl)

    def update_value(self, value: str | int) -> None:
        """Update the displayed value at runtime."""
        value_label = self.findChildren(QLabel)[0]
        if value_label:
            value_label.setText(str(value))


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

class _TaskRow(QFrame):
    """Single row in the urgent tasks list."""

    def __init__(
        self,
        title: str,
        processo: str,
        days_left: int,
        p: Palette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
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

        # Task title
        title_lbl = QLabel(title or "(sem título)")
        title_lbl.setStyleSheet(
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
        layout.addWidget(title_lbl, stretch=2)

        # Process number
        if processo:
            proc_lbl = QLabel(processo)
            proc_lbl.setStyleSheet(
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
            layout.addWidget(proc_lbl, stretch=1)

        # Days badge
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

        badge = QLabel(badge_text)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(52, 22)
        badge.setStyleSheet(
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
        layout.addWidget(badge)


# ---------------------------------------------------------------------------
# Main DashboardPage
# ---------------------------------------------------------------------------

class DashboardPage(QWidget):
    """Dashboard showing firm-wide statistics, urgent tasks, and sync status."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        user: dict[str, str],
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._dark = dark
        self._p: Palette = DARK if dark else LIGHT

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Recompute all stats from the SQLite cache and update the UI."""
        self._load_stats()
        self._load_urgent_tasks()
        self._load_sync_status()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

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
        self._content_layout.setSpacing(SP_6)

        # ---- Greeting ----
        name = self._user.get("name", "")
        greeting = self._get_greeting(name)
        self._greeting_lbl = QLabel(greeting)
        greeting_font = QFont(FONT_DISPLAY)
        greeting_font.setPixelSize(26)
        greeting_font.setWeight(QFont.Weight(FW_BOLD))
        self._greeting_lbl.setFont(greeting_font)
        self._greeting_lbl.setStyleSheet(
            f"color: {p.navy_base}; background: transparent; border: none;"
        )
        self._content_layout.addWidget(self._greeting_lbl)

        # ---- Stat cards row ----
        cards_row = QHBoxLayout()
        cards_row.setSpacing(SP_4)
        self._card_processos = StatCard("Processos Ativos", "—", "accent", self._dark)
        self._card_tarefas   = StatCard("Tarefas Hoje", "—", "warning", self._dark)
        self._card_criticos  = StatCard("Prazo Crítico", "—", "danger", self._dark)
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
        self._content_layout.addWidget(_section_heading("Tarefas Urgentes", p))
        self._tasks_container = QVBoxLayout()
        self._tasks_container.setSpacing(SP_2)
        self._content_layout.addLayout(self._tasks_container)

        # ---- Sync status ----
        self._content_layout.addWidget(_section_heading("Sincronização", p))
        self._sync_container = QVBoxLayout()
        self._sync_container.setSpacing(SP_1)
        self._content_layout.addLayout(self._sync_container)

        self._content_layout.addStretch()

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

        self._card_processos.findChildren(QLabel)[0].setText(str(active_proc))
        self._card_tarefas.findChildren(QLabel)[0].setText(str(tarefas_hoje))
        self._card_criticos.findChildren(QLabel)[0].setText(str(criticos))
        self._card_clientes.findChildren(QLabel)[0].setText(str(total_clientes))

    def _load_urgent_tasks(self) -> None:
        # Clear existing rows
        while self._tasks_container.count():
            item = self._tasks_container.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        try:
            tarefas = cache_db.get_all_records(self._conn, "Tarefas")
        except Exception:  # noqa: BLE001
            lbl = _body_label("Erro ao carregar tarefas.", self._p, muted=True)
            self._tasks_container.addWidget(lbl)
            return

        urgent: list[tuple[int, dict[str, Any]]] = []
        for r in tarefas:
            prazo_str = str(r.get("prazo_fatal", "") or r.get("prazo", "") or "")
            days = self._days_remaining(prazo_str)
            if days is not None and days <= 7:
                urgent.append((days, r))

        urgent.sort(key=lambda x: x[0])

        if not urgent:
            lbl = _body_label(
                "Nenhuma tarefa urgente nos próximos 7 dias.", self._p, muted=True
            )
            self._tasks_container.addWidget(lbl)
            return

        for days, record in urgent[:10]:
            title = str(record.get("titulo", record.get("title", record.get("cnj", ""))) or "")
            processo = str(record.get("processo", record.get("cnj", "")) or "")
            row = _TaskRow(title, processo, days, self._p)
            self._tasks_container.addWidget(row)

    def _load_sync_status(self) -> None:
        while self._sync_container.count():
            item = self._sync_container.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        p = self._p
        for base in DATA_SOURCES:
            try:
                ts = cache_db.get_last_sync(self._conn, base)
            except Exception:  # noqa: BLE001
                ts = 0.0

            if ts > 0:
                dt = datetime.fromtimestamp(ts)
                sync_text = f"{base}: {dt.strftime('%d/%m/%Y %H:%M')}"
            else:
                sync_text = f"{base}: nunca sincronizado"

            row = QHBoxLayout()
            row.setSpacing(SP_2)
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color: {p.app_success if ts > 0 else p.app_warning}; font-size: 10px; background: transparent; border: none;"
            )
            row.addWidget(dot)
            lbl = _body_label(sync_text, p, muted=True, size=FS_SM2)
            row.addWidget(lbl)
            row.addStretch()
            self._sync_container.addLayout(row)

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
        suffix = f", {name}" if name else ""
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


# Alias for SP_1 which may not be in all token sets
try:
    from notion_rpadv.theme.tokens import SP_1  # noqa: F401
except ImportError:
    SP_1 = 4
