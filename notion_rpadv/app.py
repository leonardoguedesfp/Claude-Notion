"""Main application class (QMainWindow)."""
from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from notion_bulk_edit.config import (
    APP_NAME,
    CACHE_STALE_HOURS,
    DATA_SOURCES,
    USUARIOS_LOCAIS,
    get_cache_db_path,
)
from notion_rpadv.cache import db as cache_db
from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.pages.catalogo import CatalogoPage
from notion_rpadv.pages.clientes import ClientesPage
from notion_rpadv.pages.configuracoes import ConfiguracoesPage
from notion_rpadv.pages.dashboard import DashboardPage
from notion_rpadv.pages.importar import ImportarPage
from notion_rpadv.pages.processos import ProcessosPage
from notion_rpadv.pages.tarefas import TarefasPage
from notion_rpadv.services.notion_facade import NotionFacade
from notion_rpadv.services.shortcuts import DEFAULT_SHORTCUTS, ShortcutRegistry
from notion_rpadv.theme.qss_light import build_qss
from notion_rpadv.theme.tokens import DARK, LIGHT
from notion_rpadv.widgets.command_palette import CommandPalette
from notion_rpadv.widgets.shortcuts_modal import ShortcutsModal
from notion_rpadv.widgets.sidebar import Sidebar
from notion_rpadv.widgets.status_bar import AppStatusBar
from notion_rpadv.widgets.toast import ToastManager

try:
    from notion_rpadv.pages.logs import LogsPage
except ImportError:
    LogsPage = None  # type: ignore[assignment,misc]

# Page IDs used as keys in the stacked widget registry
_PAGE_DASHBOARD  = "dashboard"
_PAGE_PROCESSOS  = "processos"
_PAGE_CLIENTES   = "clientes"
_PAGE_TAREFAS    = "tarefas"
_PAGE_CATALOGO   = "catalogo"
_PAGE_IMPORTAR   = "importar"
_PAGE_LOGS       = "logs"
_PAGE_CONFIG     = "config"

# Command palette nav_ prefix → page id mapping
_NAV_COMMANDS: dict[str, str] = {
    "nav_dashboard":  _PAGE_DASHBOARD,
    "nav_processos":  _PAGE_PROCESSOS,
    "nav_clientes":   _PAGE_CLIENTES,
    "nav_tarefas":    _PAGE_TAREFAS,
    "nav_catalogo":   _PAGE_CATALOGO,
    "nav_importar":   _PAGE_IMPORTAR,
    "nav_logs":       _PAGE_LOGS,
    "nav_config":     _PAGE_CONFIG,
}


class MainWindow(QMainWindow):
    """Root application window: sidebar + stacked pages + overlays."""

    def __init__(
        self,
        user_id: str,
        token: str,
        dark: bool = False,
    ) -> None:
        super().__init__()
        self._user_id = user_id
        self._token = token
        self._dark = dark

        # Resolve user dict
        self._user_dict: dict[str, str] = USUARIOS_LOCAIS.get(
            user_id, {"name": user_id, "initials": user_id[:2].upper(), "role": ""}
        )

        # SQLite connection — single connection shared by all pages
        db_path = get_cache_db_path()
        self._conn: sqlite3.Connection = cache_db.get_conn(db_path)

        # Services
        self._facade = NotionFacade(self._token, self._conn)
        self._sync_manager = SyncManager(self._token, self._conn)

        # Pages registry {page_id: QWidget}
        self._pages: dict[str, QWidget] = {}

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 680)

        self._build_ui()
        self._apply_theme()
        self._connect_signals()
        self._setup_shortcuts()

        # Auto-sync stale bases on startup (slight delay so UI is visible first)
        QTimer.singleShot(500, self._auto_sync_if_stale)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar ----
        self._sidebar = Sidebar(user=self._user_dict, dark=self._dark, parent=central)
        self._sidebar.page_changed.connect(self._navigate)
        root.addWidget(self._sidebar)

        # ---- Stacked widget (all pages) ----
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # Build all pages and add to stack
        self._build_pages()

        # ---- Status bar ----
        self._status_bar = AppStatusBar(self)
        self.setStatusBar(self._status_bar)

        # ---- Overlays (parented to central so they float over content) ----
        self._toast = ToastManager(central)
        self._command_palette = CommandPalette(parent=self)
        self._command_palette.action_selected.connect(self._on_command_action)
        self._command_palette.set_actions([
            {"id": "nav_dashboard",  "label": "Dashboard",               "section": "Navegação"},
            {"id": "nav_processos",  "label": "Ir para Processos",       "section": "Navegação"},
            {"id": "nav_clientes",   "label": "Ir para Clientes",        "section": "Navegação"},
            {"id": "nav_tarefas",    "label": "Ir para Tarefas",         "section": "Navegação"},
            {"id": "nav_catalogo",   "label": "Ir para Catálogo",        "section": "Navegação"},
            {"id": "nav_importar",   "label": "Importar Planilha",       "section": "Ações"},
            {"id": "nav_logs",       "label": "Ver Logs de Edição",      "section": "Ações"},
            {"id": "nav_config",     "label": "Configurações",           "section": "Ações"},
            {"id": "sync_all",       "label": "Sincronizar tudo",        "section": "Ações"},
            {"id": "toggle_theme",   "label": "Alternar tema",           "section": "Interface"},
            {"id": "show_shortcuts", "label": "Ver atalhos de teclado",  "section": "Interface"},
        ])

        # Navigate to dashboard on startup
        self._navigate(_PAGE_DASHBOARD)

    def _build_pages(self) -> None:
        """Instantiate and register every page."""
        base_kwargs: dict[str, Any] = {
            "conn":         self._conn,
            "token":        self._token,
            "user":         self._user_id,
            "facade":       self._facade,
            # BUG-21: inject shared SyncManager so pages don't create duplicates
            "sync_manager": self._sync_manager,
            "dark":         self._dark,
        }

        # Dashboard
        dashboard = DashboardPage(
            conn=self._conn, user=self._user_dict, dark=self._dark
        )
        self._add_page(_PAGE_DASHBOARD, dashboard)

        # Table pages
        self._add_page(_PAGE_PROCESSOS, ProcessosPage(**base_kwargs))
        self._add_page(_PAGE_CLIENTES,  ClientesPage(**base_kwargs))
        self._add_page(_PAGE_TAREFAS,   TarefasPage(**base_kwargs))
        self._add_page(_PAGE_CATALOGO,  CatalogoPage(**base_kwargs))

        # Utility pages
        importar = ImportarPage(
            conn=self._conn, token=self._token, user=self._user_id, dark=self._dark
        )
        importar.import_done.connect(self._on_import_done)
        self._add_page(_PAGE_IMPORTAR, importar)

        if LogsPage is not None:
            logs = LogsPage(
                conn=self._conn, token=self._token, user=self._user_id,
                facade=self._facade, dark=self._dark
            )
            self._add_page(_PAGE_LOGS, logs)

        # BUG-19: pass sync_manager to ConfiguracoesPage
        config = ConfiguracoesPage(
            current_theme="dark" if self._dark else "light",
            bindings=dict(DEFAULT_SHORTCUTS),
            sync_manager=self._sync_manager,
            dark=self._dark,
        )
        config.theme_changed.connect(self._on_theme_changed)
        config.token_changed.connect(self._on_token_changed)
        self._add_page(_PAGE_CONFIG, config)

    def _add_page(self, page_id: str, widget: QWidget) -> None:
        self._pages[page_id] = widget
        self._stack.addWidget(widget)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate(self, page_id: str) -> None:
        widget = self._pages.get(page_id)
        if widget is None:
            return
        self._stack.setCurrentWidget(widget)
        self._sidebar.set_active(page_id)

        # Refresh certain pages on navigation
        if page_id == _PAGE_DASHBOARD and hasattr(widget, "refresh"):
            widget.refresh()  # type: ignore[union-attr]
        elif page_id == _PAGE_LOGS and hasattr(widget, "refresh"):
            widget.refresh()  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        p = DARK if self._dark else LIGHT
        # BUG-10: use qss_dark for dark theme instead of always qss_light
        if self._dark:
            from notion_rpadv.theme.qss_dark import build_qss as build_qss_dark
            qss = build_qss_dark(p)
        else:
            qss = build_qss(p)
        self.setStyleSheet(qss)

    def _toggle_theme(self) -> None:
        self._dark = not self._dark
        self._apply_theme()
        self._push_toast(
            f"Tema {'escuro' if self._dark else 'claro'} ativado", "info"
        )

    def _on_theme_changed(self, theme: str) -> None:
        self._dark = theme == "dark"
        self._apply_theme()

    def _on_token_changed(self, token: str) -> None:
        self._token = token
        # BUG-11: propagate new token to facade and sync_manager
        self._facade._token = token
        self._sync_manager._token = token
        self._push_toast("Token atualizado com sucesso.", "success")

    # ------------------------------------------------------------------
    # Command palette
    # ------------------------------------------------------------------

    def _open_command_palette(self) -> None:
        self._command_palette.show_palette()

    def _on_command_action(self, action_id: str) -> None:
        if action_id in _NAV_COMMANDS:
            self._navigate(_NAV_COMMANDS[action_id])
        elif action_id == "sync_all":
            self._sync_all()
        elif action_id == "toggle_theme":
            self._toggle_theme()
        elif action_id == "show_shortcuts":
            self._show_shortcuts_modal()
        elif action_id == "new_record":
            self._push_toast("Novo registro: em desenvolvimento.", "info")

    def _show_shortcuts_modal(self) -> None:
        modal = ShortcutsModal(dark=self._dark, parent=self)
        modal.exec()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def _sync_all(self) -> None:
        self._status_bar.set_sync_status("Sincronizando…")
        self._sync_manager.sync_all()

    def _on_sync_all_done(self) -> None:
        self._status_bar.set_sync_status("Sincronizado")
        self._push_toast("Sincronização concluída.", "success")

        # Reload whichever table page is currently active
        current = self._stack.currentWidget()
        if hasattr(current, "reload"):
            current.reload()  # type: ignore[union-attr]

        # BUG-22: show max(last_sync) across all bases in status bar
        self._update_status_bar_sync_time()

    def _update_status_bar_sync_time(self) -> None:
        """BUG-22: display the most recent sync timestamp across all bases."""
        max_ts: float = 0.0
        for base in DATA_SOURCES:
            try:
                ts = cache_db.get_last_sync(self._conn, base)
                if ts > max_ts:
                    max_ts = ts
            except Exception:  # noqa: BLE001
                pass
        if max_ts > 0:
            self._status_bar.set_last_sync("Última sync", max_ts)

    def _on_sync_base_done(self, base: str, added: int, updated: int, removed: int) -> None:
        self._status_bar.set_sync_status(f"{base} sincronizado")

    def _on_sync_error(self, base: str, message: str) -> None:
        self._status_bar.set_sync_status(f"Erro: {base}")
        self._push_toast(f"Erro ao sincronizar {base}: {message}", "error")

    def _auto_sync_if_stale(self) -> None:
        """BUG-26: sync only bases whose cache is stale or never synced."""
        for base in DATA_SOURCES:
            try:
                # BUG-23: check never-synced separately from stale
                never = cache_db.is_never_synced(self._conn, base)
                stale = cache_db.is_stale(self._conn, base, CACHE_STALE_HOURS)
                if never or stale:
                    self._status_bar.set_sync_status("Sincronizando…")
                    self._sync_manager.sync_base(base)
            except Exception:  # noqa: BLE001
                self._sync_manager.sync_base(base)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Sync manager
        self._sync_manager.all_done.connect(self._on_sync_all_done)
        self._sync_manager.base_done.connect(self._on_sync_base_done)
        self._sync_manager.sync_error.connect(self._on_sync_error)

        # Facade commit results — BUG-07: signal now carries base
        self._facade.commit_started.connect(
            lambda: self._status_bar.set_sync_status("Salvando…")
        )
        self._facade.commit_finished.connect(self._on_commit_finished)
        self._facade.commit_error.connect(
            lambda msg: self._push_toast(f"Erro ao salvar: {msg}", "error")
        )

    def _on_commit_finished(self, base: str, succeeded: int, failed: int) -> None:
        self._status_bar.set_sync_status("Sincronizado")
        if failed == 0:
            self._push_toast(
                f"{succeeded} edição(ões) salva(s) no Notion.", "success"
            )
        else:
            self._push_toast(
                f"{succeeded} salvas, {failed} com erro.", "warning"
            )

    def _on_import_done(self, base: str, rows: int) -> None:
        self._push_toast(f"{rows} registro(s) importado(s) para {base}.", "success")

    # ------------------------------------------------------------------
    # Shortcuts — BUG-17: wire save/discard to active page
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        handlers = {
            "search":        self._open_command_palette,
            "toggle_theme":  self._toggle_theme,
            "nav_processos": lambda: self._navigate(_PAGE_PROCESSOS),
            "nav_clientes":  lambda: self._navigate(_PAGE_CLIENTES),
            "nav_tarefas":   lambda: self._navigate(_PAGE_TAREFAS),
            "nav_catalogo":  lambda: self._navigate(_PAGE_CATALOGO),
            "refresh":       self._refresh_current_page,
            # BUG-17: Ctrl+S → save, Escape → discard on active page
            "save":          self._save_current_page,
            "discard":       self._discard_current_page,
            "new_record":    self._new_record_current_page,
        }
        self._shortcut_registry = ShortcutRegistry(self, handlers)
        self._shortcut_registry.register_all()

    def _refresh_current_page(self) -> None:
        current = self._stack.currentWidget()
        if hasattr(current, "reload"):
            current.reload()  # type: ignore[union-attr]
        elif hasattr(current, "refresh"):
            current.refresh()  # type: ignore[union-attr]

    def _save_current_page(self) -> None:
        """BUG-17: Ctrl+S delegates to the active page's save."""
        current = self._stack.currentWidget()
        if hasattr(current, "_on_save"):
            current._on_save()  # type: ignore[union-attr]

    def _discard_current_page(self) -> None:
        """BUG-17: Escape delegates to the active page's discard."""
        current = self._stack.currentWidget()
        if hasattr(current, "_on_discard"):
            current._on_discard()  # type: ignore[union-attr]

    def _new_record_current_page(self) -> None:
        """BUG-17: Ctrl+N delegates to the active page's new-record handler."""
        current = self._stack.currentWidget()
        if hasattr(current, "_on_new"):
            current._on_new()  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Toast helper
    # ------------------------------------------------------------------

    def _push_toast(self, message: str, kind: str = "info") -> None:
        self._toast.push(message, kind=kind)

    # ------------------------------------------------------------------
    # Resize: reposition overlay
    # ------------------------------------------------------------------

    def resizeEvent(self, event: Any) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        # CommandPalette is a QDialog parented to the window — it resizes itself
        # via show_palette(). ToastManager positions its own Toast widgets.
