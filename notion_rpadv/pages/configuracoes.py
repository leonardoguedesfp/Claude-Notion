"""Settings/configuration page."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
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
from notion_rpadv.services.shortcuts_store import DEFAULT_SHORTCUTS, save_user_shortcuts
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
# P1-001 (Lote 1): "new_record" removido até existir implementação real.
_SHORTCUT_LABELS: dict[str, str] = {
    "search":       "Paleta de comandos",
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
# §7.2 ShortcutCapture — inline display ↔ capture mode for one binding.
# ---------------------------------------------------------------------------

class _ShortcutCapture(QWidget):
    """Display a key sequence as a kbd-style chip; clicking the row's
    "Editar" button flips to capture mode (QKeySequenceEdit), Enter saves
    and shows a 2-second '✓ Salvo' confirmation.
    """

    saved: Signal = Signal(str)  # new sequence string (Qt format)

    def __init__(self, sequence: str, p: "Palette", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._stack = QStackedWidget(self)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._stack)

        # Page 0: display chip
        self._display_lbl = QLabel(sequence or "—")
        self._display_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._stack.addWidget(self._display_lbl)

        # Page 1: capture editor
        self._edit = QKeySequenceEdit(QKeySequence(sequence) if sequence else QKeySequence())
        self._edit.editingFinished.connect(self._on_finished)
        self._stack.addWidget(self._edit)

        # Page 2: "✓ Salvo" confirmation
        self._saved_lbl = QLabel("✓ Salvo")
        self._stack.addWidget(self._saved_lbl)

        self._restyle()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enter_capture(self) -> None:
        """Flip from display → capture mode and grab keyboard focus."""
        self._stack.setCurrentIndex(1)
        self._edit.setFocus()
        # Visual hint while capturing.
        self._edit.setKeySequence(QKeySequence())

    def set_sequence(self, sequence: str) -> None:
        self._display_lbl.setText(sequence or "—")
        self._stack.setCurrentIndex(0)

    def keyPressEvent(self, event: object) -> None:  # type: ignore[override]
        # Esc cancels capture.
        if self._stack.currentIndex() == 1 and getattr(event, "key", lambda: 0)() == Qt.Key.Key_Escape:  # type: ignore[attr-defined]
            self._stack.setCurrentIndex(0)
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def apply_theme(self, dark: bool) -> None:
        from notion_rpadv.theme.tokens import DARK as _DARK, LIGHT as _LIGHT
        self._p = _DARK if dark else _LIGHT
        self._restyle()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_finished(self) -> None:
        seq = self._edit.keySequence().toString()
        if not seq:
            self._stack.setCurrentIndex(0)
            return
        self._display_lbl.setText(seq)
        self._stack.setCurrentIndex(2)
        self.saved.emit(seq)
        # Hold "✓ Salvo" for 2 seconds, then return to the display chip.
        QTimer.singleShot(2000, lambda: self._stack.setCurrentIndex(0))

    def _restyle(self) -> None:
        p = self._p
        chip_css = (
            f"QLabel {{"
            f" color: {p.app_fg};"
            f" font-family: 'JetBrains Mono', 'Consolas', monospace;"
            f" font-size: 12px;"
            f" background-color: {p.app_accent_soft};"
            f" border-radius: 4px;"
            f" padding: 2px 8px;"
            f" border: none; }}"
        )
        self._display_lbl.setStyleSheet(chip_css)
        # Capture editor visually aligns with the chip.
        self._edit.setStyleSheet(
            f"""
            QKeySequenceEdit {{
                background-color: {p.app_accent_soft};
                color: {p.app_accent};
                border: 1px solid {p.app_accent};
                border-radius: 4px;
                padding: 2px 6px;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 12px;
            }}
            """
        )
        self._saved_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_success};
                background-color: {p.app_success_bg};
                font-size: 12px;
                font-weight: 700;
                padding: 2px 8px;
                border-radius: 4px;
            }}
            """
        )


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

    theme_changed: Signal = Signal(str)    # "light" | "dark" | "auto"
    token_changed: Signal = Signal(str)
    shortcut_changed: Signal = Signal(str, str)  # action, new_sequence

    def __init__(
        self,
        current_theme: str = "light",
        bindings: dict[str, str] | None = None,
        sync_manager: Any = None,  # BUG-19: injected SyncManager
        conn: sqlite3.Connection | None = None,
        current_user_id: str = "",  # §7.3
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
        # §7.3: id of the user logged into this session — that row gets the
        # "Você" chip + accent-soft background.
        self._current_user_id: str = current_user_id

        self._build_ui()
        # BUG-V7: show real sync timestamps from DB at init
        if conn is not None:
            self._refresh_sync_labels(conn)

        # BUG-V2-05: keep the sync labels in lockstep with the Dashboard by
        # listening to the SyncManager's base_done signal — that's the same
        # source of truth the Dashboard uses (cache_db.get_last_sync), so the
        # two views can no longer drift to "Nunca" vs a real timestamp.
        if sync_manager is not None and conn is not None:
            try:
                sync_manager.base_done.connect(self._on_sync_base_done)
            except (TypeError, AttributeError):
                pass

    def apply_theme(self, dark: bool) -> None:
        """N5: switch palette. The page is mostly _SectionCard frames whose
        backgrounds are fixed via the global QSS, so all we need to flip is
        the page heading colour."""
        if dark == self._dark:
            return
        self._dark = dark
        self._p = DARK if dark else LIGHT
        if hasattr(self, "_heading"):
            self._heading.setStyleSheet(
                f"color: {self._p.app_fg_strong}; background: transparent; border: none;"
            )

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

        # Page heading — kept as attribute for apply_theme + uses semantic
        # token instead of brand-only navy_base (matching the V2 fixes).
        self._heading = QLabel("Configurações")
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        self._heading.setFont(heading_font)
        self._heading.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;"
        )
        layout.addWidget(self._heading)

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
        lbl = self._field_label("Tema", p)
        layout.addWidget(lbl)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(SP_4)

        self._auto_radio = QRadioButton("Auto (sistema)")
        self._light_radio = QRadioButton("Claro")
        self._dark_radio = QRadioButton("Escuro")

        for rb in (self._auto_radio, self._light_radio, self._dark_radio):
            rb.setStyleSheet(
                f"color: {p.app_fg}; font-size: {FS_MD}px; background: transparent;"
            )

        group = QButtonGroup(self)
        group.addButton(self._auto_radio)
        group.addButton(self._light_radio)
        group.addButton(self._dark_radio)

        if self._current_theme == "auto":
            self._auto_radio.setChecked(True)
        elif self._dark:
            self._dark_radio.setChecked(True)
        else:
            self._light_radio.setChecked(True)

        self._auto_radio.toggled.connect(
            lambda checked: self.theme_changed.emit("auto") if checked else None
        )
        self._light_radio.toggled.connect(
            lambda checked: self.theme_changed.emit("light") if checked else None
        )
        self._dark_radio.toggled.connect(
            lambda checked: self.theme_changed.emit("dark") if checked else None
        )

        theme_row.addWidget(self._auto_radio)
        theme_row.addWidget(self._light_radio)
        theme_row.addWidget(self._dark_radio)
        theme_row.addStretch()
        layout.addLayout(theme_row)

        # §7.4 Density segmented control
        density_lbl = self._field_label("Densidade", p)
        layout.addWidget(density_lbl)

        density_row = QHBoxLayout()
        density_row.setSpacing(0)

        seg_style_active = f"""
            QPushButton {{
                background-color: {p.app_accent};
                color: {p.app_accent_fg};
                font-size: {FS_SM2}px;
                font-weight: {FW_BOLD};
                border: 1px solid {p.app_accent};
                padding: 4px {SP_3}px;
            }}
        """
        seg_style_inactive = f"""
            QPushButton {{
                background-color: transparent;
                color: {p.app_fg};
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: 1px solid {p.app_border_strong};
                padding: 4px {SP_3}px;
            }}
            QPushButton:hover {{
                background-color: {p.app_row_hover};
            }}
        """

        compact_btn = QPushButton("Compacto")
        compact_btn.setFixedHeight(30)
        compact_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        compact_btn.setStyleSheet(
            seg_style_active + f"QPushButton {{ border-radius: 0; border-top-left-radius: {RADIUS_MD}px; border-bottom-left-radius: {RADIUS_MD}px; }}"
        )

        comfortable_btn = QPushButton("Confortável")
        comfortable_btn.setFixedHeight(30)
        comfortable_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        comfortable_btn.setStyleSheet(
            seg_style_inactive + f"QPushButton {{ border-radius: 0; border-top-right-radius: {RADIUS_MD}px; border-bottom-right-radius: {RADIUS_MD}px; border-left: none; }}"
        )

        def _on_compact() -> None:
            compact_btn.setStyleSheet(
                seg_style_active + f"QPushButton {{ border-radius: 0; border-top-left-radius: {RADIUS_MD}px; border-bottom-left-radius: {RADIUS_MD}px; }}"
            )
            comfortable_btn.setStyleSheet(
                seg_style_inactive + f"QPushButton {{ border-radius: 0; border-top-right-radius: {RADIUS_MD}px; border-bottom-right-radius: {RADIUS_MD}px; border-left: none; }}"
            )

        def _on_comfortable() -> None:
            comfortable_btn.setStyleSheet(
                seg_style_active + f"QPushButton {{ border-radius: 0; border-top-right-radius: {RADIUS_MD}px; border-bottom-right-radius: {RADIUS_MD}px; }}"
            )
            compact_btn.setStyleSheet(
                seg_style_inactive + f"QPushButton {{ border-radius: 0; border-top-left-radius: {RADIUS_MD}px; border-bottom-left-radius: {RADIUS_MD}px; }}"
            )

        compact_btn.clicked.connect(_on_compact)
        comfortable_btn.clicked.connect(_on_comfortable)

        density_row.addWidget(compact_btn)
        density_row.addWidget(comfortable_btn)
        density_row.addStretch()
        layout.addLayout(density_row)

    def _build_usuarios(self, layout: QVBoxLayout, p: Palette) -> None:
        grid = QGridLayout()
        grid.setSpacing(SP_3)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._header_label("Usuário", p), 0, 0)
        grid.addWidget(self._header_label("Iniciais", p), 0, 1)
        grid.addWidget(self._header_label("Papel", p), 0, 2)
        # §7.3: extra column on the right for the "Você" chip.
        grid.addWidget(self._header_label("", p), 0, 3)

        for row_idx, (uid, udata) in enumerate(USUARIOS_LOCAIS.items(), start=1):
            is_me = uid == self._current_user_id
            name_lbl = self._body_label(udata.get("name", uid), p)
            init_lbl = self._body_label(udata.get("initials", ""), p)
            role_lbl = self._body_label(udata.get("role", ""), p)
            if is_me:
                # §7.3: bold + accent-soft background for the active user.
                bold_css = (
                    f"color: {p.app_fg_strong}; font-weight: {FW_BOLD}; "
                    f"background-color: {p.app_accent_soft}; "
                    f"border: none; padding: 4px 8px; "
                    f"border-radius: {RADIUS_MD}px;"
                )
                for lbl in (name_lbl, init_lbl, role_lbl):
                    lbl.setStyleSheet(f"QLabel {{ {bold_css} font-size: {FS_MD}px; }}")
            grid.addWidget(name_lbl, row_idx, 0)
            grid.addWidget(init_lbl, row_idx, 1)
            grid.addWidget(role_lbl, row_idx, 2)

            if is_me:
                # §7.3: "Você" chip on the right.
                you_chip = QLabel("Você")
                you_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
                you_chip.setFixedHeight(20)
                you_chip.setStyleSheet(
                    f"""
                    QLabel {{
                        color: {p.app_accent};
                        background-color: {p.app_accent_soft};
                        font-size: {FS_SM}px;
                        font-weight: {FW_BOLD};
                        border: 1px solid {p.app_accent_soft};
                        border-radius: 10px;
                        padding: 0 8px;
                    }}
                    """
                )
                grid.addWidget(you_chip, row_idx, 3)

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

            # §7.2: inline capture widget — click "Editar" → press combo →
            # ✓ Salvo confirmation chip — no QInputDialog popup.
            capture = _ShortcutCapture(seq, p)
            capture.saved.connect(self._make_shortcut_saved_handler(action))
            grid.addWidget(capture, row_idx, 1)

            edit_btn = self._make_secondary_btn("Editar", p)
            edit_btn.setFixedHeight(26)
            edit_btn.clicked.connect(capture.enter_capture)
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

    def _make_shortcut_saved_handler(self, action: str) -> Callable[[str], None]:
        """§7.2: persist + emit when the inline ShortcutCapture fires saved()."""
        def handler(new_seq: str) -> None:
            if not new_seq:
                return
            self._bindings[action] = new_seq
            save_user_shortcuts(self._bindings)
            self.shortcut_changed.emit(action, new_seq)
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

    def _on_sync_base_done(self, base: str, *_args: object) -> None:
        """BUG-V2-05: refresh this base's sync label when SyncManager finishes
        a sync. Reads from cache_db (canonical source) so it agrees with the
        Dashboard's last-sync display."""
        from notion_rpadv.cache import db as cache_db
        if self._conn is None:
            return
        try:
            ts = cache_db.get_last_sync(self._conn, base)
        except Exception:  # noqa: BLE001
            ts = 0.0
        self.update_sync_label(base, ts)

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
