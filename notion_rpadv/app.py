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
from notion_rpadv.pages.exportar import ExportarPage
from notion_rpadv.pages.importar import ImportarPage
from notion_rpadv.pages.processos import ProcessosPage
from notion_rpadv.pages.tarefas import TarefasPage
from notion_rpadv.services.notion_facade import NotionFacade
from notion_rpadv.services.shortcuts import ShortcutRegistry
from notion_rpadv.services.shortcuts_store import load_user_shortcuts
from notion_rpadv.theme.qss_light import build_qss
from notion_rpadv.theme.tokens import LIGHT
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
_PAGE_EXPORTAR   = "exportar"
_PAGE_LOGS       = "logs"
_PAGE_CONFIG     = "config"

# Round 3a: state machine de tema removida. App roda exclusivamente em
# modo claro (LIGHT) independente do tema do sistema operacional.
# Constantes _THEME_*, _VALID_THEMES, _KEY_THEME_PREF, _SETTINGS_*,
# helper _system_prefers_dark e listeners de QStyleHints.colorScheme
# foram apagados junto com a paleta DARK e qss_dark.py.


# Command palette nav_ prefix → page id mapping
_NAV_COMMANDS: dict[str, str] = {
    "nav_dashboard":  _PAGE_DASHBOARD,
    "nav_processos":  _PAGE_PROCESSOS,
    "nav_clientes":   _PAGE_CLIENTES,
    "nav_tarefas":    _PAGE_TAREFAS,
    "nav_catalogo":   _PAGE_CATALOGO,
    "nav_importar":   _PAGE_IMPORTAR,
    "nav_exportar":   _PAGE_EXPORTAR,
    "nav_logs":       _PAGE_LOGS,
    "nav_config":     _PAGE_CONFIG,
}


class MainWindow(QMainWindow):
    """Root application window: sidebar + stacked pages + overlays."""

    def __init__(
        self,
        user_id: str,
        token: str,
    ) -> None:
        super().__init__()
        self._user_id = user_id
        self._token = token
        # Round 3a: app roda exclusivamente em modo claro. State machine
        # antigo (theme_pref / _dark / auto-resolve via OS) removida.

        # Resolve user dict
        self._user_dict: dict[str, str] = USUARIOS_LOCAIS.get(
            user_id, {"name": user_id, "initials": user_id[:2].upper(), "role": ""}
        )

        # SQLite connections.
        # BUG-OP-09: cache (records) and audit (pending_edits + edit_log)
        # live in separate files now. The migration helper copies legacy
        # rows from cache.db into audit.db on first boot post-fix and
        # flips a flag in audit.meta so subsequent boots skip the work.
        db_path = get_cache_db_path()
        # Defensive backup of the legacy cache before any migration runs.
        cache_db.backup_legacy_cache_file(db_path)
        self._conn: sqlite3.Connection = cache_db.get_cache_conn(db_path)
        self._audit_conn: sqlite3.Connection = cache_db.get_audit_conn()
        try:
            cache_db.migrate_audit_from_cache_if_needed(
                self._conn, self._audit_conn
            )
        except Exception:  # noqa: BLE001
            # Migration failure isn't fatal: legacy rows stay in cache.db
            # untouched (the .bak is preserved); the user can retry on
            # the next boot. We don't surface a toast here because the
            # status bar isn't built yet.
            pass

        # Round 4: aplica wipe de meta_user_columns quando LAYOUT_VERSION
        # bumpa. Sem isso, usuários com prefs salvas nunca veem o novo
        # layout-padrão (slugs/ordem/larguras editoriais de layout_defaults).
        try:
            from notion_rpadv.layout_defaults import LAYOUT_VERSION
            cache_db.wipe_user_columns_if_layout_changed(
                self._audit_conn, LAYOUT_VERSION,
            )
        except Exception:  # noqa: BLE001
            # Falha aqui não é fatal — usuário fica com prefs antigas até
            # próximo boot bem-sucedido. Não surface toast (status bar
            # ainda não construída).
            pass

        # Fase 3 — schema dinâmico: inicializa o singleton SchemaRegistry
        # e faz refresh das 4 bases via API (USE_DYNAMIC_SCHEMA/DYNAMIC_BASES
        # foram removidas; sempre on). Refresh é tolerante a erro: se a API
        # estiver fora ou o token inválido, o app continua usando os schemas
        # cacheados em audit.db.meta_schemas.
        from notion_bulk_edit.schema_registry import (
            boot_refresh_all,
            init_schema_registry,
        )
        self._schema_registry = init_schema_registry(self._audit_conn)
        try:
            from notion_bulk_edit.notion_api import NotionClient
            boot_refresh_all(
                NotionClient(self._token),
                self._schema_registry,
                DATA_SOURCES,
            )
        except Exception:  # noqa: BLE001
            # Erro de boot não crasha o app; cache existente continua valendo.
            pass

        # Services
        self._facade = NotionFacade(
            self._token, self._conn, audit_conn=self._audit_conn,
        )
        self._sync_manager = SyncManager(self._token, self._conn)

        # BUG-OP-11: idempotency flag — multiple workers can fire
        # auth_invalidated in quick succession (a partial save batch + a
        # background sync that started before the token expired). Only the
        # first emission shows the modal; subsequent ones are absorbed
        # silently.
        self._auth_dialog_open: bool = False

        # Pages registry {page_id: QWidget}
        self._pages: dict[str, QWidget] = {}

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 680)

        self._build_ui()
        # Round 3a: aplicação direta da paleta LIGHT no startup. Antes era
        # ``self._apply_theme()`` que escolhia entre qss_light/qss_dark.
        self.setStyleSheet(build_qss(LIGHT))
        self._connect_signals()
        self._setup_shortcuts()

        # Round 3a: listener de QStyleHints.colorSchemeChanged removido
        # — app não reage mais ao tema do sistema operacional.

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
        self._sidebar = Sidebar(user=self._user_dict, parent=central)
        self._sidebar.page_changed.connect(self._navigate)
        root.addWidget(self._sidebar)

        # ---- Stacked widget (all pages) ----
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # Build all pages and add to stack
        self._build_pages()

        # ---- Status bar ----
        # Round 3a: kwarg dark removido — paleta única LIGHT.
        self._status_bar = AppStatusBar(self)
        self.setStatusBar(self._status_bar)

        # ---- Overlays (parented to central so they float over content) ----
        self._toast = ToastManager(central)
        self._command_palette = CommandPalette(parent=self)  # §8.1
        self._command_palette.action_selected.connect(self._on_command_action)
        # Round 3a: action "toggle_theme" removida do command palette.
        self._command_palette.set_actions([
            {"id": "nav_dashboard",  "label": "Dashboard",               "section": "Navegação"},
            {"id": "nav_processos",  "label": "Ir para Processos",       "section": "Navegação"},
            {"id": "nav_clientes",   "label": "Ir para Clientes",        "section": "Navegação"},
            {"id": "nav_tarefas",    "label": "Ir para Tarefas",         "section": "Navegação"},
            {"id": "nav_catalogo",   "label": "Ir para Catálogo",        "section": "Navegação"},
            {"id": "nav_importar",   "label": "Importar Planilha",       "section": "Ações"},
            {"id": "nav_exportar",   "label": "Exportar dados",          "section": "Ações"},
            {"id": "nav_logs",       "label": "Ver Logs de Edição",      "section": "Ações"},
            {"id": "nav_config",     "label": "Configurações",           "section": "Ações"},
            {"id": "sync_all",       "label": "Sincronizar tudo",        "section": "Ações"},
            {"id": "show_shortcuts", "label": "Ver atalhos de teclado",  "section": "Interface"},
        ])

        # Navigate to dashboard on startup
        self._navigate(_PAGE_DASHBOARD)

    def _build_pages(self) -> None:
        """Instantiate and register every page."""
        # Round 3a: kwarg "dark" removido de base_kwargs e dos construtores
        # individuais. Pages são paleta única LIGHT.
        base_kwargs: dict[str, Any] = {
            "conn":         self._conn,
            # BUG-OP-09: pages need audit_conn for any cell that hits
            # pending_edits / edit_log (Save flow inside BaseTablePage).
            "audit_conn":   self._audit_conn,
            "token":        self._token,
            "user":         self._user_id,
            "facade":       self._facade,
            # BUG-21: inject shared SyncManager so pages don't create duplicates
            "sync_manager": self._sync_manager,
        }

        # Dashboard
        # §2.3: dashboard now owns a live sync panel that needs the
        # SyncManager signals — pass it through.
        dashboard = DashboardPage(
            conn=self._conn,
            user=self._user_dict,
            sync_manager=self._sync_manager,
        )
        # Auditoria 2026-04-29: signal sync_requested estava emitida (clicar
        # "Sincronizar tudo" no Dashboard fazia self.sync_requested.emit) mas
        # ninguém escutava — botão era no-op silencioso. Conectar pra _sync_all.
        try:
            dashboard.sync_requested.connect(self._sync_all)
        except (TypeError, AttributeError):
            pass
        self._add_page(_PAGE_DASHBOARD, dashboard)

        # Table pages
        # §3.2: each table page emits relation_clicked when the user double-
        # clicks a relation chip; we route them all through one navigator.
        for page_id, ctor in (
            (_PAGE_PROCESSOS, ProcessosPage),
            (_PAGE_CLIENTES, ClientesPage),
            (_PAGE_TAREFAS, TarefasPage),
            (_PAGE_CATALOGO, CatalogoPage),
        ):
            page = ctor(**base_kwargs)
            try:
                page.relation_clicked.connect(self._on_relation_clicked)
            except (TypeError, AttributeError):
                pass
            # Auditoria 2026-04-29: surface dirty conflicts via toast.
            # BUG-OP-06 deixou os signals declarados sem listener — usuário
            # perdia edições silenciosamente quando o sync detectava drift.
            model = getattr(page, "_model", None)
            if model is not None:
                try:
                    model.dirty_dropped.connect(self._on_dirty_dropped)
                    model.dirty_conflict_detected.connect(
                        self._on_dirty_conflict_detected,
                    )
                except (TypeError, AttributeError):
                    pass
            self._add_page(page_id, page)

        # Utility pages
        importar = ImportarPage(
            conn=self._conn, token=self._token, user=self._user_id,
        )
        importar.import_done.connect(self._on_import_done)
        self._add_page(_PAGE_IMPORTAR, importar)

        # Round 4 Frente 4: página de exportação (xlsx snapshot).
        exportar = ExportarPage(
            conn=self._conn, token=self._token, user=self._user_id,
            audit_conn=self._audit_conn,
        )
        exportar.toast_requested.connect(self._push_toast)
        self._add_page(_PAGE_EXPORTAR, exportar)

        if LogsPage is not None:
            # BUG-OP-09: LogsPage reads edit_log from audit.db.
            logs = LogsPage(
                conn=self._conn, token=self._token, user=self._user_id,
                facade=self._facade,
                audit_conn=self._audit_conn,
            )
            logs.toast_requested.connect(self._push_toast)
            self._add_page(_PAGE_LOGS, logs)

        # BUG-19: pass sync_manager to ConfiguracoesPage
        # BUG-V7: pass conn so ConfiguracoesPage can show real sync timestamps
        # §7.3: pass current_user_id so the Users table highlights "Você".
        # BUG-OP-07: seed the picker with the user's current bindings (defaults
        # overlaid with any saved overrides from shortcuts.json) so the UI
        # reflects what's actually active in the live ShortcutRegistry.
        # Round 3a: current_theme + dark removidos.
        config = ConfiguracoesPage(
            bindings=load_user_shortcuts(),
            sync_manager=self._sync_manager,
            conn=self._conn,
            current_user_id=self._user_id,
        )
        # Round 3a: signal theme_changed removida.
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
    # Theme: removido no Round 3a
    # ------------------------------------------------------------------
    # _resolve_dark, _apply_theme, _propagate_theme, _persist_theme_pref,
    # _toggle_theme, _on_theme_changed, _on_system_color_scheme_changed:
    # todos removidos. App roda exclusivamente em modo claro (LIGHT).
    # Aplicação da paleta acontece uma vez no __init__ via
    # ``self.setStyleSheet(build_qss(LIGHT))``.

    # Auditoria 2026-04-29: BUG-OP-06 surface — handlers que faltavam.
    # Antes, dirty_dropped e dirty_conflict_detected eram emitidos por
    # BaseTableModel.reload(preserve_dirty=True) mas ninguém escutava em
    # produção (só os testes), e o usuário perdia edições pendentes
    # silenciosamente quando o sync detectava deletion ou conflict remoto.

    def _on_dirty_dropped(self, page_id: str, key: str) -> None:
        """Edição pendente foi descartada porque a linha sumiu no Notion."""
        self._push_toast(
            f"Edição pendente perdida: o registro foi removido no Notion "
            f"(coluna {key}).",
            "warning",
        )

    def _on_dirty_conflict_detected(
        self,
        page_id: str,
        key: str,
        local_value: object,
        remote_value: object,
    ) -> None:
        """Sync detectou que o valor remoto mudou enquanto havia edição local."""
        self._push_toast(
            f"Conflito em {key}: valor mudou no Notion enquanto você editava. "
            f"Salve para sobrescrever ou descarte para manter o remoto.",
            "warning",
        )

    def _on_relation_clicked(self, target_base: str, page_id: str) -> None:
        """§3.2: navigate to the table page that owns *target_base* and
        select the row whose ``page_id`` matches. Falls back to plain
        navigation if no row is found (still useful — opens the right table)."""
        page_id_to_navigate = {
            "Processos": _PAGE_PROCESSOS,
            "Clientes": _PAGE_CLIENTES,
            "Tarefas": _PAGE_TAREFAS,
            "Catalogo": _PAGE_CATALOGO,
        }.get(target_base)
        if page_id_to_navigate is None:
            return
        self._navigate(page_id_to_navigate)
        # Try to focus the matching row.
        page = self._pages.get(page_id_to_navigate)
        if page is None:
            return
        model = getattr(page, "_model", None)
        proxy = getattr(page, "_proxy", None)
        table = getattr(page, "_table", None)
        if model is None or proxy is None or table is None:
            return
        for row in range(model.rowCount()):
            if model.get_page_id(row) == page_id:
                src_idx = model.index(row, 0)
                proxy_idx = proxy.mapFromSource(src_idx)
                if proxy_idx.isValid():
                    table.setCurrentIndex(proxy_idx)
                    table.scrollTo(proxy_idx)
                break

    def _on_token_changed(self, token: str) -> None:
        self._token = token
        # BUG-11: propagate new token to facade and sync_manager
        self._facade._token = token
        self._sync_manager._token = token
        # BUG-N7: propagate token to all pages that cache it
        for page in self._pages.values():
            if hasattr(page, "_token"):
                page._token = token  # type: ignore[union-attr]
        self._push_toast("Token atualizado com sucesso.", "success")

    # ------------------------------------------------------------------
    # BUG-OP-11: re-authentication
    # ------------------------------------------------------------------

    def _on_auth_invalidated(self) -> None:
        """Open the re-auth dialog when Notion rejects our token.

        Idempotent: if a dialog is already open we drop subsequent emissions
        on the floor instead of stacking modals. Dirty cells are *never*
        touched by this slot — they survive the failure and stay yellow
        until the user retries the save (or discards explicitly).
        """
        if self._auth_dialog_open:
            return
        self._auth_dialog_open = True
        try:
            self._status_bar.set_sync_status("Token inválido")
            choice = self._show_reauth_dialog()
            if choice == "reauthenticate":
                self._open_reauth_flow()
            else:
                # "Mais tarde": stay in degraded state — saves will keep
                # failing until the user re-authenticates, but dirty cells
                # stay visible and the user can choose when to retry.
                self._push_toast(
                    "Token inválido. Edições não serão salvas até "
                    "re-autenticar.",
                    "warning",
                )
        finally:
            self._auth_dialog_open = False

    def _show_reauth_dialog(self) -> str:
        """Modal blocker: returns 'reauthenticate' or 'later'.

        Split into its own method so tests can monkeypatch it without
        spinning up a real QMessageBox. Real implementation uses Qt's
        QMessageBox so we don't drag in a heavyweight custom dialog.
        """
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Token Notion inválido")
        box.setText(
            "O token de integração com o Notion expirou ou foi revogado."
        )
        box.setInformativeText(
            "Suas edições não salvas estão preservadas.\n\n"
            "Clique em Re-autenticar para inserir um novo token."
        )
        reauth_btn = box.addButton(
            "Re-autenticar", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton("Mais tarde", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(reauth_btn)
        box.exec()
        return "reauthenticate" if box.clickedButton() is reauth_btn else "later"

    def _open_reauth_flow(self) -> None:
        """Hand control back to the existing LoginWindow in 'first-time'
        mode so the user can paste a new secret_… token. On success, the
        new token propagates through ``_on_token_changed`` exactly like a
        manual change in Configurações.
        """
        from notion_rpadv.auth.login_window import LoginWindow
        from notion_rpadv.auth.token_store import get_token

        dlg = LoginWindow(parent=self)
        if dlg.exec():
            new_token = getattr(dlg, "_token_value", "") or get_token() or ""
            if new_token and new_token != self._token:
                self._on_token_changed(new_token)
            else:
                # User went through the dialog but kept the same token;
                # status bar still says "Token inválido" until next sync.
                self._push_toast(
                    "Mesmo token mantido. Re-autentique novamente em "
                    "Configurações se o problema persistir.",
                    "info",
                )

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
        elif action_id == "show_shortcuts":
            self._show_shortcuts_modal()
        # P1-001 (Lote 1): action "new_record" removida do command palette.
        # Round 3a: action "toggle_theme" removida (modo escuro descontinuado).

    def _show_shortcuts_modal(self) -> None:
        # Round 3a: kwarg dark removido — paleta única.
        modal = ShortcutsModal(parent=self)
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

        # BUG-EXEC-03: refresh all pages — each page reloads its own model
        # A3: preserve dirty cells across the post-sync reload. Without isto,
        # sync individual via Configurações também passa por aqui (porque
        # SyncManager emite all_done quando _pending fica vazio, mesmo após
        # um único sync_base) e descarta edições não-salvas — exatamente o
        # mesmo bug que Round A consertou em _on_base_done.
        for page in self._pages.values():
            if hasattr(page, "reload"):
                try:
                    page.reload(preserve_dirty=True)  # type: ignore[call-arg]
                except TypeError:
                    # Páginas com reload() sem kwarg (legacy) — fallback.
                    page.reload()  # type: ignore[union-attr]
            elif hasattr(page, "refresh"):
                page.refresh()  # type: ignore[union-attr]

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

        # BUG-OP-11: a single slot reacts to auth invalidation regardless of
        # whether the failure came from a save (CommitWorker), a revert
        # (_RevertWorker), or a sync (SyncWorker). The slot itself is
        # idempotent so multiple emissions in a single batch only open one
        # dialog.
        self._facade.auth_invalidated.connect(self._on_auth_invalidated)
        self._sync_manager.auth_invalidated.connect(self._on_auth_invalidated)

    def _on_commit_finished(self, base: str, results: list[dict]) -> None:
        # BUG-OP-03: results is a per-cell list. Build a toast that names
        # the failing records so the user knows which rows to revisit
        # instead of seeing "5 salvas, 2 com erro" without context.
        self._status_bar.set_sync_status("Sincronizado")
        succeeded = sum(1 for r in results if r.get("ok"))
        failed = [r for r in results if not r.get("ok")]
        if not failed:
            self._push_toast(
                f"{succeeded} edição(ões) salva(s) no Notion.", "success"
            )
            return
        # Build a "<record name> (<field label>)" snippet for up to 3
        # failures, then truncate with a pointer to the Logs page.
        snippets = self._format_failure_snippets(base, failed, max_items=3)
        if len(failed) <= 3:
            detail = ", ".join(snippets)
            kind = "warning" if succeeded > 0 else "error"
            self._push_toast(
                f"{succeeded} salvas, {len(failed)} falhas em: {detail}",
                kind,
            )
        else:
            detail = ", ".join(snippets)
            kind = "warning" if succeeded > 0 else "error"
            self._push_toast(
                f"{succeeded} salvas, {len(failed)} falhas em: {detail} "
                f"(veja Logs para detalhes)",
                kind,
            )

    def _format_failure_snippets(
        self, base: str, failed: list[dict], max_items: int = 3,
    ) -> list[str]:
        """BUG-OP-03: render `<record title> (<field label>)` for up to
        *max_items* failures so the toast points the user at the rows that
        need attention. Falls back to page_id / raw key when the title or
        schema label is missing.

        Fase 3: defensive _title_value_for_record removido — schema dinâmico
        é fonte única e cache convergiu para slugs do registry.
        """
        # Lazy imports to keep app.py startup light.
        from notion_bulk_edit.schemas import get_prop
        from notion_rpadv.cache import db as cache_db
        from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE
        title_key = _TITLE_KEY_BY_BASE.get(base, "")
        snippets: list[str] = []
        for r in failed[:max_items]:
            pid = str(r.get("page_id", ""))
            key = str(r.get("key", ""))
            # Title (record name)
            title = ""
            if title_key:
                rec = cache_db.get_record(self._conn, base, pid)
                if rec is not None:
                    title = str(rec.get(title_key) or "").strip()
            if not title:
                title = pid[:8] or "?"
            # Field label
            spec = get_prop(base, key)
            label = spec.label if spec is not None else key
            snippets.append(f"{title} ({label})")
        return snippets

    def _on_import_done(self, base: str, rows: int) -> None:
        self._push_toast(f"{rows} registro(s) importado(s) para {base}.", "success")

    # ------------------------------------------------------------------
    # Shortcuts — BUG-17: wire save/discard to active page
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        # Round 3a: "toggle_theme" removido — modo escuro descontinuado.
        handlers = {
            "search":        self._open_command_palette,
            "nav_processos": lambda: self._navigate(_PAGE_PROCESSOS),
            "nav_clientes":  lambda: self._navigate(_PAGE_CLIENTES),
            "nav_tarefas":   lambda: self._navigate(_PAGE_TAREFAS),
            "nav_catalogo":  lambda: self._navigate(_PAGE_CATALOGO),
            "refresh":       self._refresh_current_page,
            # BUG-17: Ctrl+S → save, Escape → discard on active page
            "save":          self._save_current_page,
            "discard":       self._discard_current_page,
            # P1-001 (Lote 1): "new_record" (Ctrl+N) removido até existir
            # implementação real de criação inline.
            # P3-004 (Lote 2): atalhos para picker de colunas e sidebar.
            "open_columns_picker": self._open_columns_picker_current_page,
            "toggle_sidebar":      self._toggle_sidebar,
        }
        # ShortcutRegistry.__init__ already pulls user overrides from
        # shortcuts.json so the QShortcuts created by register_all() reflect
        # any customisation the user did in a previous session (BUG-OP-07).
        self._shortcut_registry = ShortcutRegistry(self, handlers)
        self._shortcut_registry.register_all()

        # BUG-OP-07: Configurações emits shortcut_changed when the inline
        # capture saves. Connect that to the live registry so the QShortcut
        # is rebound in the same session (it already gets persisted to
        # shortcuts.json by Configurações before the emit).
        config_page = self._pages.get(_PAGE_CONFIG)
        if config_page is not None and hasattr(config_page, "shortcut_changed"):
            config_page.shortcut_changed.connect(self._on_shortcut_changed)

    def _on_shortcut_changed(self, action: str, new_sequence: str) -> None:
        """BUG-OP-07: rebind the live QShortcut so the new key sequence
        works without a restart. Persistence to disk already happened in
        Configurações.save_user_shortcuts before the signal fired."""
        self._shortcut_registry.update_binding(action, new_sequence)

    def _refresh_current_page(self) -> None:
        current = self._stack.currentWidget()
        if hasattr(current, "reload"):
            # A3: refresh manual (Ctrl+R) também preserva dirty.
            try:
                current.reload(preserve_dirty=True)  # type: ignore[call-arg]
            except TypeError:
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

    # P1-001 (Lote 1): _new_record_current_page removido junto com o
    # entry point de Ctrl+N. Reintroduzir quando criação inline for
    # implementada de verdade.

    def _open_columns_picker_current_page(self) -> None:
        """P3-004 (Lote 2): Alt+K abre o picker de colunas (Fase 4) na
        página ativa. Páginas que não são tabelas (Dashboard, Logs,
        Configurações, Importar) não têm picker — atalho é no-op.
        (Atalho mudou de Ctrl+Shift+K → Alt+K via hotfix do Round 2 por
        colisão com Notion desktop.)"""
        current = self._stack.currentWidget()
        if hasattr(current, "_open_columns_picker"):
            current._open_columns_picker()  # type: ignore[union-attr]

    def _toggle_sidebar(self) -> None:
        """P3-004 (Lote 2): Ctrl+B esconde/mostra a sidebar."""
        if hasattr(self, "_sidebar"):
            self._sidebar.setVisible(not self._sidebar.isVisible())

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
