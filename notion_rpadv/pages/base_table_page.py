"""Generic base page for all 4 data bases (Processos, Clientes, Tarefas, Catalogo)."""
from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from notion_bulk_edit.schemas import SCHEMAS, PropSpec, vocabulario
from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.models.base_table_model import BaseTableModel
from notion_rpadv.models.delegates import PropDelegate
from notion_rpadv.models.filters import TableFilterProxy
from notion_rpadv.services.notion_facade import NotionFacade
from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FS_LG,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    FW_REGULAR,
    LIGHT,
    DARK,
    Palette,
    RADIUS_MD,
    RADIUS_LG,
    SP_1,
    SP_2,
    SP_3,
    SP_4,
)
from notion_rpadv.widgets.floating_save import FloatingSaveBar


class BaseTablePage(QWidget):
    """Reusable page with search bar, table (QTableView + BaseTableModel + TableFilterProxy),
    floating save bar, and toolbar with Sync/New buttons.
    """

    commit_requested: Signal = Signal(list)  # dirty edits list

    def __init__(
        self,
        base: str,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        facade: NotionFacade,
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._base = base
        self._conn = conn
        self._token = token
        self._user = user
        self._facade = facade
        self._dark = dark

        palette: Palette = DARK if dark else LIGHT

        # Model layer
        self._model = BaseTableModel(base, conn, parent=self)
        self._proxy = TableFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        # Sync manager for this base
        self._sync_manager = SyncManager(token, conn)
        self._sync_manager.base_done.connect(self._on_base_done)
        self._sync_manager.sync_error.connect(self._on_sync_error)

        # Facade signals
        self._facade.commit_finished.connect(self._on_commit_finished)
        self._facade.commit_error.connect(self._on_commit_error)

        # Dirty tracking
        self._model.dirty_changed.connect(self._on_dirty_changed)

        self._build_ui(palette)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, p: Palette) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Toolbar row ----
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {p.app_panel};
                border-bottom: 1px solid {p.app_border};
            }}
            """
        )
        toolbar_row = QHBoxLayout(toolbar_frame)
        toolbar_row.setContentsMargins(SP_4, SP_3, SP_4, SP_3)
        toolbar_row.setSpacing(SP_2)

        # Base label
        base_lbl = QLabel(f"← {self._base}")
        base_lbl.setStyleSheet(
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
        toolbar_row.addWidget(base_lbl)
        toolbar_row.addStretch()

        # Search
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Buscar…")
        self._search_edit.setFixedHeight(32)
        self._search_edit.setFixedWidth(240)
        self._search_edit.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {p.app_bg};
                color: {p.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QLineEdit:focus {{
                border-color: {p.app_accent};
            }}
            """
        )
        self._search_edit.textChanged.connect(self._on_search_changed)
        toolbar_row.addWidget(self._search_edit)

        # Filters button
        self._filter_btn = self._make_secondary_btn("Filtros ▾", p)
        self._filter_btn.clicked.connect(self._open_filter_menu)
        toolbar_row.addWidget(self._filter_btn)

        # Sync button
        self._sync_btn = self._make_secondary_btn("Sincronizar", p)
        self._sync_btn.clicked.connect(self.sync_now)
        toolbar_row.addWidget(self._sync_btn)

        # New record button
        self._new_btn = self._make_primary_btn("+ Novo", p)
        self._new_btn.clicked.connect(self._on_new)
        toolbar_row.addWidget(self._new_btn)

        root.addWidget(toolbar_frame)

        # ---- Table ----
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setItemDelegate(PropDelegate(self._table))
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.setShowGrid(False)
        self._table.setSortingEnabled(True)
        self._table.setStyleSheet(
            f"""
            QTableView {{
                background-color: {p.app_panel};
                alternate-background-color: {p.app_row_hover};
                color: {p.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                border: none;
                gridline-color: {p.app_border};
                selection-background-color: {p.app_row_selected};
                selection-color: {p.app_fg};
            }}
            QHeaderView::section {{
                background-color: {p.app_panel};
                color: {p.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                border: none;
                border-bottom: 1px solid {p.app_border};
                padding: {SP_2}px {SP_3}px;
            }}
            QHeaderView::section:hover {{
                background-color: {p.app_row_hover};
            }}
            """
        )
        root.addWidget(self._table)

        # ---- Floating save bar (overlay) ----
        self._save_bar = FloatingSaveBar(parent=self)
        self._save_bar.save_clicked.connect(self._on_save)
        self._save_bar.discard_clicked.connect(self._on_discard)
        self._save_bar.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload data from cache."""
        self._model.reload()

    def sync_now(self) -> None:
        """Trigger sync for this base."""
        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Sincronizando…")
        self._sync_manager.sync_base(self._base)

    # ------------------------------------------------------------------
    # Layout override — keep save bar overlaid at bottom
    # ------------------------------------------------------------------

    def resizeEvent(self, event: Any) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._reposition_save_bar()

    def _reposition_save_bar(self) -> None:
        if not hasattr(self, "_save_bar"):
            return
        bar_height = 60
        margin = 16
        x = margin
        y = self.height() - bar_height - margin
        w = self.width() - 2 * margin
        self._save_bar.setGeometry(x, y, w, bar_height)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_search(text)

    def _on_dirty_changed(self, has_dirty: bool) -> None:
        count = len(self._model.get_dirty_edits())
        self._save_bar.set_count(count)
        self._save_bar.setVisible(has_dirty)
        if has_dirty:
            self._reposition_save_bar()

    def _on_save(self) -> None:
        edits = self._model.get_dirty_edits()
        if not edits:
            return
        self._save_bar.setEnabled(False)
        self._facade.commit_edits(edits, self._user)

    def _on_discard(self) -> None:
        self._model.discard_dirty()
        self._save_bar.setVisible(False)

    def _on_new(self) -> None:
        # New record: not yet implemented — show info toast via parent
        pass

    def _on_commit_finished(self, success: int, errors: int) -> None:
        self._save_bar.setEnabled(True)
        if errors == 0:
            self._model.clear_dirty()
            self._save_bar.setVisible(False)
        # Parent window will show toast via facade signal

    def _on_commit_error(self, message: str) -> None:
        self._save_bar.setEnabled(True)

    def _on_base_done(self, base: str, added: int, updated: int, removed: int) -> None:
        if base == self._base:
            self._sync_btn.setEnabled(True)
            self._sync_btn.setText("Sincronizar")
            self._model.reload()

    def _on_sync_error(self, base: str, message: str) -> None:
        if base == self._base:
            self._sync_btn.setEnabled(True)
            self._sync_btn.setText("Sincronizar")

    # ------------------------------------------------------------------
    # Filter menu
    # ------------------------------------------------------------------

    def _open_filter_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {(DARK if self._dark else LIGHT).app_panel};
                color: {(DARK if self._dark else LIGHT).app_fg};
                border: 1px solid {(DARK if self._dark else LIGHT).app_border};
                border-radius: {RADIUS_MD}px;
                padding: {SP_2}px;
            }}
            QMenu::item {{
                padding: {SP_2}px {SP_3}px;
            }}
            """
        )

        schema = SCHEMAS.get(self._base, {})
        for key, spec in schema.items():
            if spec.tipo in ("select", "multi_select") and spec.opcoes:
                label_action = QWidgetAction(menu)
                col_label = QLabel(f"  {spec.label}")
                col_label.setStyleSheet(
                    f"""
                    QLabel {{
                        color: {(DARK if self._dark else LIGHT).app_fg_muted};
                        font-size: {FS_SM}px;
                        font-weight: {FW_BOLD};
                        padding: {SP_1}px {SP_3}px;
                        background: transparent;
                    }}
                    """
                )
                label_action.setDefaultWidget(col_label)
                menu.addAction(label_action)

                col_index = list(schema.keys()).index(key) if key in list(schema.keys()) else -1

                for option in spec.opcoes:
                    wa = QWidgetAction(menu)
                    cb = QCheckBox(f"  {option}")
                    cb.setChecked(True)
                    cb.setStyleSheet(
                        f"""
                        QCheckBox {{
                            color: {(DARK if self._dark else LIGHT).app_fg};
                            font-size: {FS_MD}px;
                            padding: {SP_1}px {SP_3}px;
                            background: transparent;
                        }}
                        """
                    )

                    def _make_handler(k: str, opt: str, checkbox: QCheckBox) -> Any:
                        def handler(checked: bool) -> None:
                            # Rebuild active values for this column
                            parent_menu = menu
                            # Collect all checked options for this column
                            # Simple approach: clear and set filter based on all current checkboxes
                            pass
                        return handler

                    cb.toggled.connect(_make_handler(key, option, cb))
                    wa.setDefaultWidget(cb)
                    menu.addAction(wa)

                menu.addSeparator()

        menu.exec(self._filter_btn.mapToGlobal(QPoint(0, self._filter_btn.height())))

    # ------------------------------------------------------------------
    # Button factory helpers
    # ------------------------------------------------------------------

    def _make_primary_btn(self, text: str, p: Palette) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {p.app_accent};
                color: {p.app_accent_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_BOLD};
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{
                background-color: {p.app_accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {p.navy_dark};
            }}
            QPushButton:disabled {{
                background-color: {p.app_border};
                color: {p.app_fg_subtle};
            }}
            """
        )
        return btn

    def _make_secondary_btn(self, text: str, p: Palette) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {p.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QPushButton:hover {{
                background-color: {p.app_row_hover};
                border-color: {p.app_border_strong};
            }}
            QPushButton:pressed {{
                background-color: {p.app_accent_soft};
            }}
            QPushButton:disabled {{
                color: {p.app_fg_subtle};
            }}
            """
        )
        return btn
