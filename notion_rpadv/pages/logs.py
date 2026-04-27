"""Edit log page — shows history of changes with revert option."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from notion_rpadv.services.log_service import get_log_entries
from notion_rpadv.services.notion_facade import NotionFacade
from notion_rpadv.theme.tokens import (
    DARK,
    FONT_BODY,
    FONT_DISPLAY,
    FONT_MONO,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    LIGHT,
    Palette,
    RADIUS_MD,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)
from notion_rpadv.widgets.modal import ConfirmModal

_COLUMNS = ["Data/hora", "Usuário", "Base", "Campo", "Valor anterior", "Valor novo", "Ação"]
_COL_DATETIME = 0
_COL_USER = 1
_COL_BASE = 2
_COL_KEY = 3
_COL_OLD = 4
_COL_NEW = 5
_COL_ACTION = 6


class LogsPage(QWidget):
    """Page displaying the full history of changes with revert capability."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        facade: NotionFacade,
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._token = token
        self._user = user
        self._facade = facade
        self._dark = dark
        self._p: Palette = DARK if dark else LIGHT

        self._entries: list[dict[str, Any]] = []

        # Connect revert result
        self._facade.revert_finished.connect(self._on_revert_finished)

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload log entries from SQLite and repopulate the table."""
        try:
            self._entries = get_log_entries(self._conn, limit=200)
        except Exception:  # noqa: BLE001
            self._entries = []
        self._populate_table()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        root = QVBoxLayout(self)
        root.setContentsMargins(SP_8, SP_6, SP_8, SP_6)
        root.setSpacing(SP_4)

        # Header row
        header_row = QHBoxLayout()
        heading = QLabel("Logs de Edição")
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        heading.setFont(heading_font)
        heading.setStyleSheet(f"color: {p.navy_base}; background: transparent; border: none;")
        header_row.addWidget(heading)
        header_row.addStretch()

        refresh_btn = QPushButton("↻ Atualizar")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent; color: {p.app_fg};
                border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px; font-size: {FS_SM2}px;
            }}
            QPushButton:hover {{ background: {p.app_row_hover}; }}
            """
        )
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        root.addLayout(header_row)

        # Sub-label
        sub = QLabel("Histórico das últimas 200 edições. Clique em Reverter para desfazer uma alteração.")
        sub.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM2}px; background: transparent; border: none;"
        )
        root.addWidget(sub)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {p.app_panel};
                alternate-background-color: {p.app_row_hover};
                color: {p.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                selection-background-color: {p.app_row_selected};
                selection-color: {p.app_fg};
            }}
            QHeaderView::section {{
                background-color: {p.app_panel};
                color: {p.app_fg_muted};
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                border: none;
                border-bottom: 1px solid {p.app_border};
                padding: {SP_2}px {SP_3}px;
            }}
            """
        )
        root.addWidget(self._table)

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _populate_table(self) -> None:
        p = self._p
        self._table.setRowCount(len(self._entries))

        for row_idx, entry in enumerate(self._entries):
            is_reverted = bool(entry.get("reverted", 0))

            # Datetime
            applied_at = float(entry.get("applied_at", 0))
            if applied_at:
                dt_str = datetime.fromtimestamp(applied_at).strftime("%d/%m/%Y %H:%M")
            else:
                dt_str = "—"
            self._set_item(row_idx, _COL_DATETIME, dt_str, is_reverted, mono=True)

            # User
            self._set_item(row_idx, _COL_USER, str(entry.get("user", "")), is_reverted)

            # Base
            self._set_item(row_idx, _COL_BASE, str(entry.get("base", "")), is_reverted)

            # Key/Campo
            self._set_item(row_idx, _COL_KEY, str(entry.get("key", "")), is_reverted)

            # Old value
            old_val = entry.get("old_value")
            self._set_item(row_idx, _COL_OLD, self._fmt_value(old_val), is_reverted)

            # New value
            new_val = entry.get("new_value")
            self._set_item(row_idx, _COL_NEW, self._fmt_value(new_val), is_reverted)

            # Action column: revert button or reverted badge
            if is_reverted:
                badge = QLabel("Revertido")
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setStyleSheet(
                    f"""
                    QLabel {{
                        color: {p.app_fg_subtle};
                        font-size: {FS_SM}px;
                        background-color: {p.app_row_hover};
                        border-radius: {RADIUS_MD}px;
                        padding: 2px 8px;
                        border: none;
                    }}
                    """
                )
                self._table.setCellWidget(row_idx, _COL_ACTION, badge)
            else:
                btn = QPushButton("Reverter")
                btn.setFixedHeight(24)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {p.app_danger_bg};
                        color: {p.app_danger};
                        font-size: {FS_SM}px;
                        font-weight: {FW_MEDIUM};
                        border: 1px solid {p.app_danger};
                        border-radius: {RADIUS_MD}px;
                        padding: 0 8px;
                    }}
                    QPushButton:hover {{ background-color: {p.app_danger}; color: white; }}
                    """
                )
                log_id = int(entry.get("id", 0))
                btn.clicked.connect(self._make_revert_handler(log_id, row_idx))
                self._table.setCellWidget(row_idx, _COL_ACTION, btn)

        self._table.resizeColumnsToContents()

    def _set_item(
        self, row: int, col: int, text: str, muted: bool, mono: bool = False
    ) -> None:
        p = self._p
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if muted:
            item.setForeground(QColor(p.app_fg_subtle))
        if mono:
            font = QFont(FONT_MONO)
            font.setPixelSize(FS_SM)
            item.setFont(font)
        self._table.setItem(row, col, item)

    @staticmethod
    def _fmt_value(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    # ------------------------------------------------------------------
    # Revert logic
    # ------------------------------------------------------------------

    def _make_revert_handler(self, log_id: int, row_idx: int) -> Any:
        def handler() -> None:
            entry = self._entries[row_idx] if row_idx < len(self._entries) else {}
            campo = str(entry.get("key", ""))
            base = str(entry.get("base", ""))
            confirm = ConfirmModal(
                "Reverter alteração",
                f"Reverter campo '{campo}' da base {base} para o valor anterior?",
                confirm_label="Reverter",
                danger=True,
                parent=self,
            )
            if confirm.exec_and_get():
                self._facade.revert_log_entry(log_id, self._user)
        return handler

    def _on_revert_finished(self, success: bool, message: str) -> None:
        # BUG-N19: distinguish success from failure instead of always refreshing silently
        from notion_rpadv.widgets.toast import ToastManager
        toast = self.findChild(ToastManager)
        if success:
            if toast:
                toast.push("Reversão aplicada com sucesso.", kind="success")
        else:
            if toast:
                toast.push(f"Erro ao reverter: {message}", kind="error")
        self.refresh()
