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
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from notion_bulk_edit.schemas import SCHEMAS
from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.models.base_table_model import BaseTableModel
from notion_rpadv.models.delegates import PropDelegate
from notion_rpadv.models.filters import TableFilterProxy
from notion_rpadv.services.notion_facade import NotionFacade
from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FONT_DISPLAY,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    LIGHT,
    DARK,
    Palette,
    RADIUS_MD,
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
        sync_manager: SyncManager | None = None,
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

        # BUG-21: use injected SyncManager instead of creating a duplicate
        if sync_manager is not None:
            self._sync_manager = sync_manager
        else:
            # Fallback for callers that don't inject one
            self._sync_manager = SyncManager(token, conn)
        self._sync_manager.base_done.connect(self._on_base_done)
        self._sync_manager.sync_error.connect(self._on_sync_error)

        # Facade signals — BUG-07: signal now carries base
        self._facade.commit_finished.connect(self._on_commit_finished)
        self._facade.commit_error.connect(self._on_commit_error)

        # Dirty tracking
        self._model.dirty_changed.connect(self._on_dirty_changed)

        # Reload → update meta count + resize columns
        self._model.modelReset.connect(self._update_meta)
        self._model.modelReset.connect(self._resize_columns_to_header)

        # BUG-06: per-column active filter state
        self._active_filters: dict[str, set[str]] = {}

        self._build_ui(palette)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, p: Palette) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Toolbar ----
        self._toolbar = self._build_toolbar(p)
        root.addWidget(self._toolbar)

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
        # BUG-V2: give each column a minimum width based on header text
        header = self._table.horizontalHeader()
        header.setMinimumSectionSize(80)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(header.ResizeMode.Interactive)
        header.setStretchLastSection(False)
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

    def _build_toolbar(self, p: Palette) -> QFrame:
        """Build the spec-compliant toolbar QFrame."""
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

        # 1. Title label — base name
        self._toolbar_title = QLabel(self._base)
        self._toolbar_title.setObjectName("ToolbarTitle")
        title_font = QFont(FONT_DISPLAY)
        title_font.setPixelSize(22)
        title_font.setWeight(QFont.Weight(400))
        self._toolbar_title.setFont(title_font)
        self._toolbar_title.setStyleSheet(
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
        row.addWidget(self._toolbar_title)

        # 2. Meta label — row count
        self._toolbar_meta = QLabel("— registros")
        self._toolbar_meta.setObjectName("ToolbarMeta")
        self._toolbar_meta.setStyleSheet(
            f"""
            QLabel#ToolbarMeta {{
                font-size: 11px;
                color: {p.app_fg_subtle};
                letter-spacing: 0.04em;
                text-transform: uppercase;
                font-weight: 600;
                background: transparent;
                border: none;
                margin-right: 4px;
            }}
            """
        )
        row.addWidget(self._toolbar_meta)

        # 3. Spacer
        row.addStretch()

        # 4. Search input
        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("SearchInput")
        self._search_edit.setPlaceholderText("Pesquisar… Ctrl+K")
        self._search_edit.setFixedWidth(280)
        self._search_edit.setFixedHeight(32)
        self._search_edit.setStyleSheet(
            f"""
            QLineEdit#SearchInput {{
                background-color: {p.app_panel};
                color: {p.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QLineEdit#SearchInput:focus {{
                border-color: {p.app_accent};
            }}
            """
        )
        self._search_edit.textChanged.connect(self._proxy.set_search)
        row.addWidget(self._search_edit)

        # 5. Filtros button
        self._filter_btn = QPushButton("Filtros ▾")
        self._filter_btn.setObjectName("BtnGhost")
        self._filter_btn.setFixedHeight(32)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.setStyleSheet(
            f"""
            QPushButton#BtnGhost {{
                background-color: transparent;
                color: {p.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QPushButton#BtnGhost:hover {{
                background-color: {p.app_row_hover};
                border-color: {p.app_border_strong};
            }}
            QPushButton#BtnGhost:pressed {{
                background-color: {p.app_accent_soft};
            }}
            """
        )
        self._filter_btn.clicked.connect(self._open_filter_menu)
        row.addWidget(self._filter_btn)

        # 6. Vertical divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFixedWidth(1)
        divider.setStyleSheet(
            f"QFrame {{ background-color: {p.app_border}; border: none; }}"
        )
        row.addWidget(divider)

        # 7. Sincronizar button
        self._sync_btn = QPushButton("Sincronizar")
        self._sync_btn.setObjectName("BtnSecondary")
        self._sync_btn.setFixedHeight(32)
        self._sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_btn.setStyleSheet(
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
        self._sync_btn.clicked.connect(self.sync_now)
        row.addWidget(self._sync_btn)

        # 8. + Novo button
        self._new_btn = QPushButton("+ Novo")
        self._new_btn.setObjectName("BtnPrimary")
        self._new_btn.setFixedHeight(32)
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.setStyleSheet(
            f"""
            QPushButton#BtnPrimary {{
                background-color: {p.app_accent};
                color: {p.app_accent_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_BOLD};
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton#BtnPrimary:hover {{
                background-color: {p.app_accent_hover};
            }}
            QPushButton#BtnPrimary:pressed {{
                background-color: {p.navy_dark};
            }}
            QPushButton#BtnPrimary:disabled {{
                background-color: {p.app_border};
                color: {p.app_fg_subtle};
            }}
            """
        )
        self._new_btn.clicked.connect(self._on_new)
        row.addWidget(self._new_btn)

        return toolbar

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
    # Meta update
    # ------------------------------------------------------------------

    def _update_meta(self) -> None:
        """Refresh the ToolbarMeta label with the current row count."""
        n = self._model.rowCount()
        self._toolbar_meta.setText(f"{n} registros")

    def _resize_columns_to_header(self) -> None:
        """BUG-V2: set each column width to at least the header text width."""
        if not hasattr(self, "_table"):
            return
        header = self._table.horizontalHeader()
        fm = header.fontMetrics()
        for col in range(self._model.columnCount()):
            label = self._model.headerData(col, Qt.Orientation.Horizontal) or ""
            min_w = max(80, fm.horizontalAdvance(str(label)) + 24)
            if header.sectionSize(col) < min_w:
                header.resizeSection(col, min_w)
            header.setSectionResizeMode(col, header.ResizeMode.Interactive)

    # ------------------------------------------------------------------
    # Layout override — keep save bar overlaid at bottom
    # ------------------------------------------------------------------

    def resizeEvent(self, event: Any) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._reposition_save_bar()

    def _reposition_save_bar(self) -> None:
        # §4.1 delegate positioning to FloatingSaveBar.reposition() for consistency
        if not hasattr(self, "_save_bar"):
            return
        self._save_bar.reposition()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_dirty_changed(self, has_dirty: bool) -> None:
        count = len(self._model.get_dirty_edits())
        self._save_bar.set_count(count, self._base)  # §4.2 include base name
        self._save_bar.setVisible(has_dirty)
        if has_dirty:
            self._reposition_save_bar()

    def _on_save(self) -> None:
        edits = self._model.get_dirty_edits()
        if not edits:
            return
        self._save_bar.setEnabled(False)
        # BUG-07: pass base so facade can emit it in commit_finished
        self._facade.commit_edits(edits, self._user, self._base)

    def _on_discard(self) -> None:
        self._model.discard_dirty()
        self._save_bar.setVisible(False)

    def _on_new(self) -> None:
        pass

    def _on_commit_finished(self, base: str, success: int, errors: int) -> None:
        self._save_bar.setEnabled(True)
        # BUG-07: only clear dirty for this page's base
        if base != self._base:
            return
        if errors == 0:
            self._model.clear_dirty()
            self._save_bar.setVisible(False)

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
        p = DARK if self._dark else LIGHT
        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {p.app_panel};
                color: {p.app_fg};
                border: 1px solid {p.app_border};
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
                        color: {p.app_fg_muted};
                        font-size: {FS_SM}px;
                        font-weight: {FW_BOLD};
                        padding: {SP_1}px {SP_3}px;
                        background: transparent;
                    }}
                    """
                )
                label_action.setDefaultWidget(col_label)
                menu.addAction(label_action)

                # BUG-06: determine source model column index for this key
                try:
                    source_col = self._model._cols.index(key)
                except ValueError:
                    source_col = -1

                # Current active filter for this column (None = all allowed)
                active = self._active_filters.get(key)

                for option in spec.opcoes:
                    wa = QWidgetAction(menu)
                    cb = QCheckBox(f"  {option}")
                    # If no filter active, all boxes start checked
                    cb.setChecked(active is None or option in active)
                    cb.setStyleSheet(
                        f"""
                        QCheckBox {{
                            color: {p.app_fg};
                            font-size: {FS_MD}px;
                            padding: {SP_1}px {SP_3}px;
                            background: transparent;
                        }}
                        """
                    )

                    # BUG-06: closure captures key, option, source_col
                    def _make_handler(k: str, opt: str, col: int) -> Any:
                        def handler(checked: bool) -> None:
                            # Initialise filter set from all options if not yet active
                            if k not in self._active_filters:
                                self._active_filters[k] = set(SCHEMAS.get(self._base, {}).get(k).opcoes)  # type: ignore[union-attr]
                            if checked:
                                self._active_filters[k].add(opt)
                            else:
                                self._active_filters[k].discard(opt)
                            # Apply to proxy (None removes the filter, restoring all rows)
                            if col >= 0:
                                active_set = self._active_filters[k]
                                all_opts = set(SCHEMAS.get(self._base, {}).get(k).opcoes)  # type: ignore[union-attr]
                                # If all options checked, remove the filter entirely
                                if active_set >= all_opts:
                                    self._proxy.set_col_filter(col, None)
                                else:
                                    self._proxy.set_col_filter(col, active_set)
                        return handler

                    cb.toggled.connect(_make_handler(key, option, source_col))
                    wa.setDefaultWidget(cb)
                    menu.addAction(wa)

                menu.addSeparator()

        menu.exec(self._filter_btn.mapToGlobal(QPoint(0, self._filter_btn.height())))
