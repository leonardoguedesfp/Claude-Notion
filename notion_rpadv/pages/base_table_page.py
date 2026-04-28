"""Generic base page for all 4 data bases (Processos, Clientes, Tarefas, Catalogo)."""
from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QPaintEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from notion_bulk_edit.config import DATA_SOURCES
from notion_bulk_edit.schemas import SCHEMAS
from notion_rpadv.cache import db as cache_db
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
from notion_rpadv.widgets.empty_state import EmptyState
from notion_rpadv.widgets.filter_bar import FilterBar
from notion_rpadv.widgets.floating_save import FloatingSaveBar


# ---------------------------------------------------------------------------
# Style factories — single source of truth for the toolbar's inline styles.
# Used both at build time (initial rendering) and on theme toggle (apply_theme).
# ---------------------------------------------------------------------------

def _toolbar_title_css(p: Palette) -> str:
    return (
        f"QLabel#ToolbarTitle {{"
        f" font-family: 'Playfair Display', 'Cormorant Garamond', Georgia, serif;"
        f" font-size: 22px; font-weight: 400;"
        f" color: {p.app_fg_strong};"
        f" background: transparent; border: none; margin-right: 14px; }}"
    )


def _toolbar_meta_css(p: Palette) -> str:
    return (
        f"QLabel#ToolbarMeta {{"
        f" font-size: 11px; color: {p.app_fg_subtle};"
        f" letter-spacing: 0.04em; text-transform: uppercase;"
        f" font-weight: 600; background: transparent; border: none;"
        f" margin-right: 4px; }}"
    )


def _search_input_css(p: Palette) -> str:
    return (
        f"QLineEdit#SearchInput {{"
        f" background-color: {p.app_panel}; color: {p.app_fg};"
        f" font-family: '{FONT_BODY}', 'Segoe UI', Arial, sans-serif;"
        f" font-size: {FS_MD}px;"
        f" border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;"
        f" padding: 0 {SP_3}px; }}"
        f"QLineEdit#SearchInput:focus {{ border-color: {p.app_accent}; }}"
    )


def _btn_ghost_css(p: Palette) -> str:
    return (
        f"QPushButton#BtnGhost {{"
        f" background-color: transparent; color: {p.app_fg};"
        f" font-family: '{FONT_BODY}', 'Segoe UI', Arial, sans-serif;"
        f" font-size: {FS_SM2}px; font-weight: {FW_MEDIUM};"
        f" border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;"
        f" padding: 0 {SP_3}px; }}"
        f"QPushButton#BtnGhost:hover {{ background-color: {p.app_row_hover};"
        f" border-color: {p.app_border_strong}; }}"
        f"QPushButton#BtnGhost:pressed {{ background-color: {p.app_accent_soft}; }}"
    )


def _btn_secondary_css(p: Palette) -> str:
    return (
        f"QPushButton#BtnSecondary {{"
        f" background-color: transparent; color: {p.app_fg};"
        f" font-family: '{FONT_BODY}', 'Segoe UI', Arial, sans-serif;"
        f" font-size: {FS_SM2}px; font-weight: {FW_MEDIUM};"
        f" border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;"
        f" padding: 0 {SP_3}px; }}"
        f"QPushButton#BtnSecondary:hover {{ background-color: {p.app_row_hover};"
        f" border-color: {p.app_border_strong}; }}"
        f"QPushButton#BtnSecondary:pressed {{ background-color: {p.app_accent_soft}; }}"
        f"QPushButton#BtnSecondary:disabled {{ color: {p.app_fg_subtle}; }}"
    )


class _BaseTableView(QTableView):
    """§3.4 QTableView that paints the area below the last row with the
    page surface colour instead of leaving the default white.

    Without this, the user sees a hard white rectangle when the table has
    fewer rows than the viewport — visually disconnected from the rest of
    the page chrome (cream/navy depending on theme).
    """

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tail_color = QColor(p.app_bg)

    def set_palette(self, p: Palette) -> None:
        self._tail_color = QColor(p.app_bg)
        self.viewport().update()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        super().paintEvent(event)
        # Find the y-coordinate just below the last visible row.
        viewport = self.viewport()
        if viewport is None:
            return
        model = self.model()
        if model is None:
            return
        rows = model.rowCount()
        if rows <= 0:
            # Whole viewport — but the EmptyState handles full-empty cases.
            # Painting here would clobber the table backdrop. No-op.
            return
        last_idx = model.index(rows - 1, 0)
        last_rect = self.visualRect(last_idx)
        bottom = last_rect.bottom() + 1
        if bottom >= viewport.height():
            return  # viewport already filled by rows
        painter = QPainter(viewport)
        painter.fillRect(
            0, bottom, viewport.width(), viewport.height() - bottom,
            QBrush(self._tail_color),
        )
        painter.end()


def _btn_primary_css(p: Palette) -> str:
    return (
        f"QPushButton#BtnPrimary {{"
        f" background-color: {p.app_accent}; color: {p.app_accent_fg};"
        f" font-family: '{FONT_BODY}', 'Segoe UI', Arial, sans-serif;"
        f" font-size: {FS_SM2}px; font-weight: {FW_BOLD};"
        f" border: none; border-radius: {RADIUS_MD}px;"
        f" padding: 0 {SP_4}px; }}"
        f"QPushButton#BtnPrimary:hover {{ background-color: {p.app_accent_hover}; }}"
        f"QPushButton#BtnPrimary:pressed {{ background-color: {p.navy_dark}; }}"
        f"QPushButton#BtnPrimary:disabled {{ background-color: {p.app_border};"
        f" color: {p.app_fg_subtle}; }}"
    )


class BaseTablePage(QWidget):
    """Reusable page with search bar, table (QTableView + BaseTableModel + TableFilterProxy),
    floating save bar, and toolbar with Sync/New buttons.
    """

    commit_requested: Signal = Signal(list)  # dirty edits list
    # §3.2: emitted when the user double-clicks a relation chip — carries
    # (target_base, page_id) so MainWindow can navigate to the related row.
    relation_clicked: Signal = Signal(str, str)

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
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__(parent)
        self._base = base
        self._conn = conn
        # BUG-OP-09: a separate audit connection is passed by MainWindow.
        # In-memory tests that use a single conn for both schemas can
        # leave audit_conn=None — the model/page falls back to `conn`.
        self._audit_conn: sqlite3.Connection = audit_conn or conn
        self._token = token
        self._user = user
        self._facade = facade
        self._dark = dark

        palette: Palette = DARK if dark else LIGHT

        # Model layer
        # Fase 4: passa user_id para o model resolver prefs em
        # meta_user_columns. None mantém defaults do schema.
        self._model = BaseTableModel(
            base, conn, parent=self, audit_conn=self._audit_conn,
            user_id=user,
        )
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
        # §9 / BUG-N2: swap between the table and EmptyState whenever the
        # source model is reloaded (sync, manual reload, etc).
        self._model.modelReset.connect(self._refresh_empty_state)

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

        # ---- Filter bar (§3.9) ----
        # Hidden until the user activates at least one column filter; shows
        # one chip per active filter + a Limpar todos link.
        self._filter_bar = FilterBar(dark=self._dark, parent=self)
        self._filter_bar.filter_removed.connect(self._on_filter_chip_removed)
        self._filter_bar.clear_all_clicked.connect(self._on_clear_all_filters)
        root.addWidget(self._filter_bar)

        # ---- Table ----
        # §3.4: custom subclass paints the area below the last row with the
        # active surface colour so the table integrates with the page bg.
        self._table = _BaseTableView(p)
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
        # §3.2: double-click a relation cell → emit relation_clicked so the
        # parent window can navigate to the related record's page.
        self._table.doubleClicked.connect(self._on_table_double_clicked)
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
        # §9 / BUG-N2: stack the table and the empty state so we can swap
        # them in-place when the base is fully empty (sync returned 0 rows).
        # The empty state is only used for "no records at all" — filtered
        # zero-results keep the table visible (handled elsewhere).
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._table)
        self._empty_state = EmptyState(
            base_name=self._base,
            on_sync=self.sync_now,
            on_create=self._on_new,
            dark=self._dark,
            parent=self._content_stack,
        )
        self._content_stack.addWidget(self._empty_state)
        root.addWidget(self._content_stack)

        # Fase 4: header context menu — clique direito no cabeçalho de
        # uma coluna oferece "Esconder coluna" (Componente 7). Não permite
        # ocultar a coluna do título — o handler protege contra isso.
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

        # ---- Floating save bar (overlay) ----
        self._save_bar = FloatingSaveBar(parent=self)
        self._save_bar.save_clicked.connect(self._on_save)
        self._save_bar.discard_clicked.connect(self._on_discard)
        self._save_bar.setVisible(False)

        # Initial state: source model already loaded in __init__ → reflect it now.
        self._refresh_empty_state()

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

        # 5b. Colunas button (Fase 4 — picker de visibilidade)
        self._cols_btn = QPushButton("⋮ Colunas")
        self._cols_btn.setObjectName("BtnGhost")
        self._cols_btn.setFixedHeight(32)
        self._cols_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cols_btn.setStyleSheet(_btn_ghost_css(p))
        self._cols_btn.clicked.connect(self._open_columns_picker)
        row.addWidget(self._cols_btn)

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

    def reload(self, preserve_dirty: bool = False) -> None:
        """Reload data from cache.

        A3: ``preserve_dirty=True`` propaga o flag para o model.reload, que
        snapshota e restaura `_dirty` em torno do reset (igual ao que o
        Round A já fazia em ``_on_base_done``). Usado por chamadas externas
        que disparam reload no fim de um sync (``_on_sync_all_done``) ou
        em refresh manual (``_refresh_current_page``) para que edições
        não-salvas sobrevivam.
        """
        self._model.reload(preserve_dirty=preserve_dirty)

    def apply_theme(self, dark: bool) -> None:
        """N5: rebuild palette-derived inline styles after a theme toggle.

        Most of the table chrome flows through the global QSS (button object
        names, QHeaderView::section, QTableView selectors), so we only need
        to refresh the inline overrides set in ``_build_toolbar`` and
        ``_build_ui``. Subclasses with extra inline styles can override and
        call super().
        """
        if dark == self._dark:
            return
        self._dark = dark
        new_p: Palette = DARK if dark else LIGHT
        self._restyle_for_palette(new_p)
        # The empty state caches its own palette — refresh it too.
        if hasattr(self, "_empty_state"):
            es_apply = getattr(self._empty_state, "apply_theme", None)
            if callable(es_apply):
                es_apply(dark)
        # Floating save bar caches its own styling.
        if hasattr(self, "_save_bar"):
            sb_apply = getattr(self._save_bar, "apply_theme", None)
            if callable(sb_apply):
                sb_apply(dark)

    def _restyle_for_palette(self, p: Palette) -> None:
        """Re-apply the inline stylesheets that depend on the palette."""
        # Toolbar background
        if hasattr(self, "_toolbar"):
            self._toolbar.setStyleSheet(
                f"QFrame#Toolbar {{ background-color: {p.app_bg}; "
                f"border-bottom: 1px solid {p.app_border}; }}"
            )
        # §3.4: refresh the empty-tail colour so the area below the last
        # row tracks the current theme.
        if hasattr(self, "_table") and isinstance(self._table, _BaseTableView):
            self._table.set_palette(p)
        # Table & header colours
        if hasattr(self, "_table"):
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
        # Toolbar button + input styles share the same colour vocabulary,
        # so we mass-update by walking known attributes. Each branch silently
        # tolerates absent attributes (subclasses may strip features).
        for attr, css_factory in (
            ("_toolbar_title", _toolbar_title_css),
            ("_toolbar_meta", _toolbar_meta_css),
            ("_search_edit", _search_input_css),
            ("_filter_btn", _btn_ghost_css),
            ("_cols_btn", _btn_ghost_css),  # Fase 4
            ("_sync_btn", _btn_secondary_css),
            ("_new_btn", _btn_primary_css),
        ):
            w = getattr(self, attr, None)
            if w is not None:
                w.setStyleSheet(css_factory(p))

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

    def _refresh_empty_state(self) -> None:
        """§9: show EmptyState when the SOURCE model has zero rows.

        We deliberately read ``self._model.rowCount()`` (source) and not the
        proxy — a filter that hides every row should keep the table visible
        with the existing "no results" state, not flip to the big empty state.
        §9.3: also disable the toolbar's search and +Novo buttons so the user
        understands there is nothing to act on yet.
        """
        is_empty = self._model.rowCount() == 0
        # Switch the stacked area
        if hasattr(self, "_content_stack") and hasattr(self, "_empty_state"):
            target = self._empty_state if is_empty else self._table
            self._content_stack.setCurrentWidget(target)
        # Update the empty-state footer with the latest sync status
        if is_empty and hasattr(self, "_empty_state"):
            self._empty_state.set_last_sync_text(self._format_last_sync_for_empty())
        # §9.3: gate the search input and "+ Novo" button on having rows
        if hasattr(self, "_search_edit"):
            self._search_edit.setEnabled(not is_empty)
        if hasattr(self, "_new_btn"):
            self._new_btn.setEnabled(not is_empty)
        if hasattr(self, "_filter_btn"):
            self._filter_btn.setEnabled(not is_empty)
        # Fase 4: o picker de colunas faz sentido mesmo sem registros
        # (usuário pode querer pré-configurar antes do primeiro sync). Sem
        # desabilitar.

    def _format_last_sync_for_empty(self) -> str:
        """Build the EmptyState footer text from the cache's last sync ts."""
        try:
            from notion_rpadv.cache import db as cache_db
            ts = cache_db.get_last_sync(self._conn, self._base)
        except Exception:  # noqa: BLE001
            ts = 0.0
        if ts <= 0:
            return "Ainda não sincronizado · 0 registros"
        import time
        from datetime import datetime
        elapsed = time.time() - ts
        if elapsed < 60:
            rel = "agora há pouco"
        elif elapsed < 3600:
            rel = f"há {int(elapsed // 60)} min"
        elif elapsed < 86_400:
            rel = f"há {int(elapsed // 3600)} h"
        else:
            rel = datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")
        return f"Última sync: {rel} · 0 registros"

    def _resize_columns_to_header(self) -> None:
        """BUG-V2-08 / §3.1: ensure each column is wide enough to show its
        full header text after the QSS transforms it (uppercase + bold +
        letter-spacing), AND respects an explicit floor declared in the
        schema's ``min_width_px``.

        ``header.fontMetrics()`` reflects the widget's default font, NOT the
        font enforced by QSS, so we measure with an explicit bold QFont sized
        to match the QSS header rule. We also account for the uppercase
        transform, the per-character letter-spacing, and the section padding.
        """
        if not hasattr(self, "_table"):
            return
        from PySide6.QtGui import QFont, QFontMetrics
        from notion_bulk_edit.schemas import get_prop

        header = self._table.horizontalHeader()
        # Header QSS: font-size 10px, weight 700, letter-spacing 0.06em,
        # padding 8px 12px on each side, plus the sort indicator (~16px).
        header_font = QFont(FONT_BODY)
        header_font.setPixelSize(10)
        header_font.setBold(True)
        fm = QFontMetrics(header_font)
        letter_spacing_px = max(1, int(round(10 * 0.06)))  # 0.06em ≈ 1px
        padding_px = 12 * 2  # left + right
        sort_indicator_px = 16

        # Fase 4: lê do cache do model (recalculado em reload) em vez de
        # consultar colunas_visiveis(base) repetidamente.
        cols = self._model.cols()
        for col in range(self._model.columnCount()):
            label = self._model.headerData(col, Qt.Orientation.Horizontal) or ""
            text = str(label).upper()  # QSS text-transform: uppercase
            text_w = fm.horizontalAdvance(text) + letter_spacing_px * max(0, len(text) - 1)
            font_min = max(80, text_w + padding_px + sort_indicator_px)

            # §3.1: schema-declared floor wins when larger than the font-aware
            # estimate. This is what guarantees "Cliente principal" never
            # truncates to "Cliente Princip." regardless of the runtime font.
            schema_min = 0
            if col < len(cols):
                spec = get_prop(self._base, cols[col])
                if spec is not None and spec.min_width_px:
                    schema_min = int(spec.min_width_px)

            min_w = max(font_min, schema_min)
            header.setSectionResizeMode(col, header.ResizeMode.Interactive)
            if header.sectionSize(col) < min_w:
                header.resizeSection(col, min_w)
        # §3.1: full-label tooltips on header are served by the model's
        # headerData(ToolTipRole) override — no per-column setup here.
        header.setMinimumSectionSize(min(96, max(80, padding_px + sort_indicator_px + 24)))

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

    # ------------------------------------------------------------------
    # §3.9 Filter bar
    # ------------------------------------------------------------------

    def _refresh_filter_bar(self) -> None:
        """Sync the FilterBar to the current ``self._active_filters`` state.

        A filter is shown only when its set is a *strict* subset of the
        column's full option list — otherwise it represents "everything
        selected" which is the same as no filter.
        """
        from notion_bulk_edit.schemas import SCHEMAS, get_prop
        active_for_bar: dict[str, tuple[str, int]] = {}
        schema = SCHEMAS.get(self._base, {})
        for key, selected in self._active_filters.items():
            spec = get_prop(self._base, key)
            if spec is None:
                continue
            all_opts = set(spec.opcoes or schema.get(key).opcoes or ())  # type: ignore[union-attr]
            if not selected or selected >= all_opts:
                continue  # no-op filter
            active_for_bar[key] = (spec.label, len(selected))
        self._filter_bar.set_filters(active_for_bar)

    def _on_filter_chip_removed(self, key: str) -> None:
        """§3.9: × on a chip clears that single column's filter."""
        # Fase 4: usa cache do model (recalculado em reload).
        self._active_filters.pop(key, None)
        cols = self._model.cols()
        if key in cols:
            self._proxy.set_col_filter(cols.index(key), None)
        self._refresh_filter_bar()

    def _on_clear_all_filters(self) -> None:
        """§3.9: 'Limpar todos' clears every active column filter at once."""
        # Fase 4: usa cache do model (recalculado em reload).
        cols = self._model.cols()
        for key in list(self._active_filters.keys()):
            if key in cols:
                self._proxy.set_col_filter(cols.index(key), None)
        self._active_filters.clear()
        self._refresh_filter_bar()

    def _on_table_double_clicked(self, index: Any) -> None:
        """§3.2: navigate to the related record when a relation cell is
        double-clicked. The cell stores list[page_id] in EditRole; we pick
        the first id and emit (target_base, page_id) for MainWindow."""
        from notion_bulk_edit.schemas import get_prop
        if not index.isValid():
            return
        # Fase 4: usa cache do model (recalculado em reload).
        cols = self._model.cols()
        col = index.column()
        if col >= len(cols):
            return
        spec = get_prop(self._base, cols[col])
        if spec is None or spec.tipo != "relation" or not spec.target_base:
            return
        # Navigate to source-model index for the raw page_ids list.
        src_index = self._proxy.mapToSource(index) if hasattr(self._proxy, "mapToSource") else index
        raw = self._model.data(src_index, Qt.ItemDataRole.EditRole)
        if isinstance(raw, list) and raw:
            self.relation_clicked.emit(spec.target_base, str(raw[0]))

    def _on_dirty_changed(self, has_dirty: bool) -> None:
        count = len(self._model.get_dirty_edits())
        self._save_bar.set_count(count, self._base)  # §4.2 include base name
        self._save_bar.setVisible(has_dirty)
        if has_dirty:
            self._reposition_save_bar()

    def _on_save(self) -> None:
        # BUG-OP-01/02: persist each dirty cell as a pending_edit BEFORE
        # firing the CommitWorker so the worker can later call
        # mark_edit_applied(id, user) on each successful API call. Without a
        # real id, the move from pending_edits → edit_log never happens and
        # the Logs page stays empty.
        edits = self._model.flush_dirty_to_pending()
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

    def _on_commit_finished(self, base: str, results: list[dict]) -> None:
        # BUG-OP-03: results is a per-cell list with shape:
        #   {"page_id": str, "key": str, "edit_id": int, "ok": bool, "error": str|None}
        # We clear dirty only for the cells that succeeded; failures stay
        # visibly yellow so the user can retry without re-typing.
        self._save_bar.setEnabled(True)
        # BUG-07: only clear dirty for this page's base
        if base != self._base:
            return
        success_keys: list[tuple[str, str]] = [
            (r["page_id"], r["key"]) for r in results if r.get("ok")
        ]
        if success_keys:
            self._model.clear_dirty(cells_to_clear=success_keys)
        # Save bar visibility tracks the live dirty set: hide only when
        # there is nothing left pending.
        self._save_bar.setVisible(bool(self._model._dirty))

    def _on_commit_error(self, message: str) -> None:
        self._save_bar.setEnabled(True)

    def _on_base_done(self, base: str, added: int, updated: int, removed: int) -> None:
        if base == self._base:
            self._sync_btn.setEnabled(True)
            self._sync_btn.setText("Sincronizar")
            # BUG-OP-06: preserve unsaved edits across the sync-induced
            # reload. Without this flag, every completed sync nukes the
            # user's in-flight dirty cells silently.
            self._model.reload(preserve_dirty=True)

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
                                    self._active_filters.pop(k, None)
                                else:
                                    self._proxy.set_col_filter(col, active_set)
                            # §3.9: keep the FilterBar in sync after every toggle.
                            self._refresh_filter_bar()
                        return handler

                    cb.toggled.connect(_make_handler(key, option, source_col))
                    wa.setDefaultWidget(cb)
                    menu.addAction(wa)

                menu.addSeparator()

        menu.exec(self._filter_btn.mapToGlobal(QPoint(0, self._filter_btn.height())))

    # ------------------------------------------------------------------
    # Fase 4 — picker de colunas + header context menu
    # ------------------------------------------------------------------

    def _qmenu_stylesheet(self, p: Palette) -> str:
        """CSS compartilhado pelo picker e pelo header context menu.
        Espelha o pattern usado em ``_open_filter_menu``."""
        return (
            f"QMenu {{"
            f" background-color: {p.app_panel}; color: {p.app_fg};"
            f" border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px; padding: {SP_2}px; }}"
            f"QMenu::item {{ padding: {SP_2}px {SP_3}px; }}"
            f"QMenu::item:selected {{"
            f" background-color: {p.app_row_hover}; }}"
            f"QMenu::separator {{ height: 1px;"
            f" background-color: {p.app_border};"
            f" margin: {SP_1}px {SP_2}px; }}"
        )

    def _open_columns_picker(self) -> None:
        """Fase 4: abre QMenu com checkboxes de visibilidade. Toggle salva
        em ``meta_user_columns``; reload do model reflete a mudança.

        Layout: seção "Visíveis" (atual ``_cols`` na ordem) → divider →
        seção "Ocultas" (resto do schema, ordenado por ``default_order``)
        → divider → "Restaurar padrão". Coluna do título aparece
        desabilitada.
        """
        p: Palette = DARK if self._dark else LIGHT
        menu = QMenu(self)
        menu.setStyleSheet(self._qmenu_stylesheet(p))

        # Schema completo da base (todas as keys disponíveis).
        schema = SCHEMAS.get(self._base, {})
        visible_set = set(self._model.cols())

        # Title slug — não permite ocultar.
        from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE
        title_key = _TITLE_KEY_BY_BASE.get(self._base, "")

        section_label_css = (
            f"QLabel {{"
            f" color: {p.app_fg_muted}; font-size: {FS_SM}px;"
            f" font-weight: {FW_BOLD}; padding: {SP_1}px {SP_3}px;"
            f" background: transparent; }}"
        )
        checkbox_css = (
            f"QCheckBox {{"
            f" color: {p.app_fg}; font-size: {FS_MD}px;"
            f" padding: {SP_1}px {SP_3}px; background: transparent; }}"
            f"QCheckBox:disabled {{ color: {p.app_fg_subtle}; }}"
        )

        # Seção "Visíveis" — atual _cols, mantém ordem.
        if self._model.cols():
            label_visible = QWidgetAction(menu)
            lbl = QLabel("  Visíveis")
            lbl.setStyleSheet(section_label_css)
            label_visible.setDefaultWidget(lbl)
            menu.addAction(label_visible)

            for slug in self._model.cols():
                spec = schema.get(slug)
                if spec is None:
                    continue
                wa = QWidgetAction(menu)
                cb = QCheckBox(f"  {spec.label}")
                cb.setChecked(True)
                if slug == title_key:
                    cb.setEnabled(False)
                    cb.setToolTip(
                        "A coluna do título não pode ser ocultada.",
                    )
                cb.setStyleSheet(checkbox_css)
                cb.toggled.connect(self._make_columns_picker_handler(slug))
                wa.setDefaultWidget(cb)
                menu.addAction(wa)

        # Seção "Ocultas" — slugs do schema fora de _cols, ordenados pela
        # ordem canônica da API (default_order ascending).
        # SCHEMAS proxy retorna PropSpec mas não expõe default_order — vamos
        # ler do schema parsed do registry para ordenar corretamente.
        from notion_bulk_edit.schema_registry import get_schema_registry
        try:
            parsed = get_schema_registry()._schemas.get(self._base, {})
        except RuntimeError:
            parsed = {}
        properties = parsed.get("properties", {})
        hidden_with_order = [
            (properties.get(k, {}).get("default_order", 999), k)
            for k in schema if k not in visible_set
        ]
        hidden_with_order.sort(key=lambda t: t[0])
        hidden_keys = [k for _, k in hidden_with_order]

        if hidden_keys:
            menu.addSeparator()
            label_hidden = QWidgetAction(menu)
            lbl_h = QLabel("  Ocultas")
            lbl_h.setStyleSheet(section_label_css)
            label_hidden.setDefaultWidget(lbl_h)
            menu.addAction(label_hidden)

            for slug in hidden_keys:
                spec = schema.get(slug)
                if spec is None:
                    continue
                wa = QWidgetAction(menu)
                cb = QCheckBox(f"  {spec.label}")
                cb.setChecked(False)
                cb.setStyleSheet(checkbox_css)
                cb.toggled.connect(self._make_columns_picker_handler(slug))
                wa.setDefaultWidget(cb)
                menu.addAction(wa)

        menu.addSeparator()

        # Botão "Restaurar padrão"
        reset_action = QAction("Restaurar padrão", menu)
        reset_action.triggered.connect(self._reset_columns_to_default)
        menu.addAction(reset_action)

        menu.exec(
            self._cols_btn.mapToGlobal(QPoint(0, self._cols_btn.height())),
        )

    def _make_columns_picker_handler(self, slug: str) -> Any:
        """Retorna closure que persiste a nova lista de visíveis e recarrega
        o model. Closure captura ``slug`` para que o handler saiba qual
        coluna está sendo togglada."""
        def handler(checked: bool) -> None:
            dsid = DATA_SOURCES.get(self._base)
            if dsid is None:
                return  # base desconhecida — silent no-op

            current = list(self._model.cols())
            if checked:
                # Adiciona ao final (ordem do schema é preservada na primeira
                # visualização; novas adições vão pro fim).
                if slug not in current:
                    current.append(slug)
            else:
                current = [k for k in current if k != slug]

            cache_db.set_user_columns(
                self._audit_conn, self._user, dsid, current,
            )
            # Recarrega — _cols é recalculado a partir do registry. Preserva
            # edições não-salvas (pattern do A3/Round A).
            self._model.reload(preserve_dirty=True)
        return handler

    def _reset_columns_to_default(self) -> None:
        """Apaga prefs do usuário para esta base; próximo reload cai no
        default do schema (default_visible=True)."""
        dsid = DATA_SOURCES.get(self._base)
        if dsid is None:
            return
        cache_db.clear_user_columns(self._audit_conn, self._user, dsid)
        self._model.reload(preserve_dirty=True)

    def _on_header_context_menu(self, pos: QPoint) -> None:
        """Fase 4: clique direito no header oferece 'Esconder coluna'."""
        header = self._table.horizontalHeader()
        section = header.logicalIndexAt(pos)
        cols = self._model.cols()
        if section < 0 or section >= len(cols):
            return
        slug = cols[section]

        # Não permite ocultar coluna do título.
        from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE
        if slug == _TITLE_KEY_BY_BASE.get(self._base, ""):
            return

        p: Palette = DARK if self._dark else LIGHT
        menu = QMenu(self)
        menu.setStyleSheet(self._qmenu_stylesheet(p))

        schema = SCHEMAS.get(self._base, {})
        spec = schema.get(slug)
        label = spec.label if spec is not None else slug

        hide_action = QAction(f"Esconder coluna '{label}'", menu)
        hide_action.triggered.connect(
            lambda: self._make_columns_picker_handler(slug)(False),
        )
        menu.addAction(hide_action)

        menu.exec(header.mapToGlobal(pos))
