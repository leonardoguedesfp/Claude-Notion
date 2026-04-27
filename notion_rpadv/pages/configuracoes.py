"""Settings/configuration page."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import sqlite3

from notion_bulk_edit.config import (
    APP_BUILD,
    APP_NAME,
    APP_VERSION,
    DATA_SOURCES,
    USUARIOS_LOCAIS,
)
from notion_rpadv.services.shortcuts import DEFAULT_SHORTCUTS
from notion_rpadv.theme.tokens import (
    DARK,
    FONT_BODY,
    FONT_DISPLAY,
    FS_LG,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    LIGHT,
    Palette,
    RADIUS_LG,
    RADIUS_MD,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)

# Human-readable shortcut labels (shared with ShortcutsModal)
_SHORTCUT_LABELS: dict[str, str] = {
    "search":       "Paleta de comandos",
    "new_record":   "Novo registro",
    "save":         "Salvar alterações",
    "discard":      "Descartar",
    "refresh":      "Atualizar",
    "toggle_theme": "Alternar tema",
    "nav_processos":"Ir para Processos",
    "nav_clientes": "Ir para Clientes",
    "nav_tarefas":  "Ir para Tarefas",
    "nav_catalogo": "Ir para Catálogo",
}


# ---------------------------------------------------------------------------
# Section card
# ---------------------------------------------------------------------------

class _SectionCard(QFrame):
    """A card with a bold title and a content area below."""

    def __init__(self, title: str, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {p.app_panel};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_LG}px;
            }}
            """
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(SP_4, SP_4, SP_4, SP_4)
        self._layout.setSpacing(SP_3)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_fg_strong};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_LG}px;
                font-weight: {FW_BOLD};
                background: transparent;
                border: none;
            }}
            """
        )
        self._layout.addWidget(title_lbl)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {p.app_divider}; border: none;")
        self._layout.addWidget(div)

    def content_layout(self) -> QVBoxLayout:
        return self._layout


# ---------------------------------------------------------------------------
# ConfiguracoesPage
# ---------------------------------------------------------------------------

class ConfiguracoesPage(QWidget):
    """Settings page with 6 grouped sections."""

    theme_changed: Signal = Signal(str)   # "light" | "dark"
    token_changed: Signal = Signal(str)

    def __init__(
        self,
        current_theme: str = "light",
        bindings: dict[str, str] | None = None,
        sync_manager: Any = None,  # BUG-19: injected SyncManager
        conn: sqlite3.Connection | None = None,
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark = dark
        self._p: Palette = DARK if dark else LIGHT
        self._current_theme = current_theme
        self._bindings = dict(bindings or DEFAULT_SHORTCUTS)
        self._sync_labels: dict[str, QLabel] = {}
        self._sync_manager = sync_manager
        self._conn = conn

        self._build_ui()
        # BUG-V7: show real sync timestamps from DB at init
        if conn is not None:
            self._refresh_sync_labels(conn)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet(f"background-color: {p.app_bg};")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(SP_8, SP_6, SP_8, SP_8)
        layout.setSpacing(SP_6)

        # Page heading
        heading = QLabel("Configurações")
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        heading.setFont(heading_font)
        heading.setStyleSheet(f"color: {p.navy_base}; background: transparent; border: none;")
        layout.addWidget(heading)

        # ---- Section 1: Integração ----
        sec1 = _SectionCard("Integração", p)
        self._build_integracao(sec1.content_layout(), p)
        layout.addWidget(sec1)

        # ---- Section 2: Sincronização ----
        sec2 = _SectionCard("Sincronização", p)
        self._build_sincronizacao(sec2.content_layout(), p)
        layout.addWidget(sec2)

        # ---- Section 3: Aparência ----
        sec3 = _SectionCard("Aparência", p)
        self._build_aparencia(sec3.content_layout(), p)
        layout.addWidget(sec3)

        # ---- Section 4: Usuários ----
        sec4 = _SectionCard("Usuários", p)
        self._build_usuarios(sec4.content_layout(), p)
        layout.addWidget(sec4)

        # ---- Section 5: Atalhos ----
        sec5 = _SectionCard("Atalhos de Teclado", p)
        self._build_atalhos(sec5.content_layout(), p)
        layout.addWidget(sec5)

        # ---- Section 6: Sobre ----
        sec6 = _SectionCard("Sobre", p)
        self._build_sobre(sec6.content_layout(), p)
        layout.addWidget(sec6)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_integracao(self, layout: QVBoxLayout, p: Palette) -> None:
        lbl = self._field_label("Token de Integração Notion", p)
        layout.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(SP_2)

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("secret_…")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setFixedHeight(34)
        self._style_input(self._token_edit, p)
        row.addWidget(self._token_edit)

        verify_btn = self._make_secondary_btn("Verificar", p)
        verify_btn.clicked.connect(self._on_verify_token)
        row.addWidget(verify_btn)

        save_token_btn = self._make_primary_btn("Salvar token", p)
        save_token_btn.clicked.connect(self._on_save_token)
        row.addWidget(save_token_btn)

        layout.addLayout(row)

        self._token_status = QLabel("")
        self._token_status.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; background: transparent; border: none;"
        )
        layout.addWidget(self._token_status)

    def _build_sincronizacao(self, layout: QVBoxLayout, p: Palette) -> None:
        for base in DATA_SOURCES:
            row = QHBoxLayout()
            row.setSpacing(SP_3)

            base_lbl = QLabel(base)
            base_lbl.setFixedWidth(100)
            base_lbl.setStyleSheet(
                f"color: {p.app_fg}; font-size: {FS_MD}px; font-weight: {FW_MEDIUM}; background: transparent; border: none;"
            )
            row.addWidget(base_lbl)

            sync_lbl = QLabel("—")
            sync_lbl.setStyleSheet(
                f"color: {p.app_fg_muted}; font-size: {FS_SM2}px; background: transparent; border: none;"
            )
            self._sync_labels[base] = sync_lbl
            row.addWidget(sync_lbl, stretch=1)

            sync_btn = self._make_secondary_btn(f"Sincronizar {base}", p)
            sync_btn.clicked.connect(self._make_sync_handler(base))
            row.addWidget(sync_btn)

            layout.addLayout(row)

    def _build_aparencia(self, layout: QVBoxLayout, p: Palette) -> None:
        row = QHBoxLayout()
        row.setSpacing(SP_4)

        lbl = self._field_label("Tema", p)
        layout.addWidget(lbl)

        self._light_radio = QRadioButton("Claro")
        self._dark_radio = QRadioButton("Escuro")

        for rb in (self._light_radio, self._dark_radio):
            rb.setStyleSheet(
                f"color: {p.app_fg}; font-size: {FS_MD}px; background: transparent;"
            )

        group = QButtonGroup(self)
        group.addButton(self._light_radio)
        group.addButton(self._dark_radio)

        if self._dark:
            self._dark_radio.setChecked(True)
        else:
            self._light_radio.setChecked(True)

        self._light_radio.toggled.connect(
            lambda checked: self.theme_changed.emit("light") if checked else None
        )
        self._dark_radio.toggled.connect(
            lambda checked: self.theme_changed.emit("dark") if checked else None
        )

        row.addWidget(self._light_radio)
        row.addWidget(self._dark_radio)
        row.addStretch()
        layout.addLayout(row)

    def _build_usuarios(self, layout: QVBoxLayout, p: Palette) -> None:
        grid = QGridLayout()
        grid.setSpacing(SP_3)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._header_label("Usuário", p), 0, 0)
        grid.addWidget(self._header_label("Iniciais", p), 0, 1)
        grid.addWidget(self._header_label("Papel", p), 0, 2)

        for row_idx, (uid, udata) in enumerate(USUARIOS_LOCAIS.items(), start=1):
            grid.addWidget(self._body_label(udata.get("name", uid), p), row_idx, 0)
            grid.addWidget(self._body_label(udata.get("initials", ""), p), row_idx, 1)
            grid.addWidget(self._body_label(udata.get("role", ""), p), row_idx, 2)

        layout.addLayout(grid)

    def _build_atalhos(self, layout: QVBoxLayout, p: Palette) -> None:
        grid = QGridLayout()
        grid.setSpacing(SP_2)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._header_label("Ação", p), 0, 0)
        grid.addWidget(self._header_label("Atalho", p), 0, 1)
        grid.addWidget(self._header_label("", p), 0, 2)

        for row_idx, (action, seq) in enumerate(self._bindings.items(), start=1):
            label_text = _SHORTCUT_LABELS.get(action, action.replace("_", " ").title())
            grid.addWidget(self._body_label(label_text, p), row_idx, 0)

            seq_lbl = QLabel(seq or "—")
            seq_lbl.setStyleSheet(
                f"""
                QLabel {{
                    color: {p.app_fg};
                    font-family: "JetBrains Mono", "Consolas", monospace;
                    font-size: {FS_SM2}px;
                    background-color: {p.app_accent_soft};
                    border-radius: {RADIUS_MD}px;
                    padding: 2px 8px;
                    border: none;
                }}
                """
            )
            grid.addWidget(seq_lbl, row_idx, 1)

            edit_btn = self._make_secondary_btn("Editar", p)
            edit_btn.setFixedHeight(26)
            edit_btn.clicked.connect(self._make_edit_shortcut_handler(action, seq_lbl))
            grid.addWidget(edit_btn, row_idx, 2)

        layout.addLayout(grid)

    def _build_sobre(self, layout: QVBoxLayout, p: Palette) -> None:
        info = [
            (APP_NAME, True),
            (f"Versão {APP_VERSION} (build {APP_BUILD})", False),
            ("", False),
            ("Sistema de gestão de processos jurídicos para o escritório RPADV Advocacia.", False),
            ("Integrado ao Notion via API pública.", False),
        ]
        for text, bold in info:
            if not text:
                layout.addSpacing(SP_1)
                continue
            lbl = QLabel(text)
            style = (
                f"color: {p.app_fg_strong}; font-weight: {FW_BOLD};" if bold
                else f"color: {p.app_fg_muted};"
            )
            lbl.setStyleSheet(
                f"QLabel {{ {style} font-size: {FS_MD}px; background: transparent; border: none; }}"
            )
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_verify_token(self) -> None:
        token = self._token_edit.text().strip()
        if not token:
            self._token_status.setText("Cole o token primeiro.")
            return
        try:
            from notion_bulk_edit.notion_api import NotionClient
            NotionClient(token).me()
            self._token_status.setText("✓ Token válido")
            self._token_status.setStyleSheet(
                f"color: {self._p.app_success}; font-size: {FS_SM}px; background: transparent; border: none;"
            )
        except Exception as exc:  # noqa: BLE001
            self._token_status.setText(f"✗ Inválido: {exc}")
            self._token_status.setStyleSheet(
                f"color: {self._p.app_danger}; font-size: {FS_SM}px; background: transparent; border: none;"
            )

    def _on_save_token(self) -> None:
        token = self._token_edit.text().strip()
        if not token:
            return
        from notion_rpadv.auth.token_store import set_token
        set_token(token)
        self.token_changed.emit(token)
        self._token_status.setText("Token salvo.")

    def _make_sync_handler(self, base: str) -> Callable[[], None]:
        def handler() -> None:
            # BUG-N6: actually trigger the sync, not just update label text
            if self._sync_manager:
                self._sync_manager.sync_base(base)
            lbl = self._sync_labels.get(base)
            if lbl:
                lbl.setText("Sincronizando…")
        return handler

    def _make_edit_shortcut_handler(self, action: str, label: QLabel) -> Callable[[], None]:
        def handler() -> None:
            from PySide6.QtWidgets import QInputDialog
            current = self._bindings.get(action, "")
            new_seq, ok = QInputDialog.getText(
                self, "Editar atalho", f"Novo atalho para '{action}':", text=current
            )
            if ok and new_seq:
                self._bindings[action] = new_seq
                label.setText(new_seq)
        return handler

    def update_sync_label(self, base: str, ts: float) -> None:
        """Update the sync timestamp label for a base (called externally)."""
        lbl = self._sync_labels.get(base)
        if lbl and ts > 0:
            dt = datetime.fromtimestamp(ts)
            lbl.setText(dt.strftime("%d/%m/%Y %H:%M"))
        elif lbl:
            lbl.setText("Nunca")

    def _refresh_sync_labels(self, conn: sqlite3.Connection) -> None:
        """BUG-V7: populate sync labels from DB at startup."""
        from notion_rpadv.cache import db as cache_db
        for base in DATA_SOURCES:
            try:
                ts = cache_db.get_last_sync(conn, base)
                self.update_sync_label(base, ts)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Widget factory helpers
    # ------------------------------------------------------------------

    def _field_label(self, text: str, p: Palette) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; font-weight: {FW_MEDIUM}; background: transparent; border: none;"
        )
        return lbl

    def _header_label(self, text: str, p: Palette) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; font-weight: {FW_BOLD}; letter-spacing: 1px; background: transparent; border: none;"
        )
        return lbl

    def _body_label(self, text: str, p: Palette) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {p.app_fg}; font-size: {FS_MD}px; background: transparent; border: none;"
        )
        return lbl

    def _style_input(self, widget: QWidget, p: Palette) -> None:
        widget.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {p.app_bg};
                color: {p.app_fg};
                font-size: {FS_MD}px;
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QLineEdit:focus {{ border-color: {p.app_accent}; }}
            """
        )

    def _make_primary_btn(self, text: str, p: Palette) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {p.app_accent}; color: {p.app_accent_fg};
                font-size: {FS_SM2}px; font-weight: {FW_BOLD};
                border: none; border-radius: {RADIUS_MD}px; padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{ background-color: {p.app_accent_hover}; }}
            """
        )
        return btn

    def _make_secondary_btn(self, text: str, p: Palette) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent; color: {p.app_fg};
                font-size: {FS_SM2}px; font-weight: {FW_MEDIUM};
                border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px; padding: 0 {SP_3}px;
            }}
            QPushButton:hover {{ background-color: {p.app_row_hover}; }}
            """
        )
        return btn


# SP_1 compatibility
try:
    from notion_rpadv.theme.tokens import SP_1  # noqa: F401
except ImportError:
    SP_1 = 4
