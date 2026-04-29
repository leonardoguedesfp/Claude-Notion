"""Login window — split-panel: navy art left + cream form right."""
from __future__ import annotations

import pathlib

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from notion_bulk_edit.config import USUARIOS_LOCAIS
from notion_bulk_edit.notion_api import NotionAuthError, NotionClient
from notion_rpadv.auth.token_store import set_token
from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FONT_DISPLAY,
    FONT_MONO,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    FW_REGULAR,
    FW_SEMIBOLD,
    LIGHT,
    RADIUS_MD,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
)

_P = LIGHT
_ASSETS_DIR: pathlib.Path = pathlib.Path(__file__).parent.parent / "assets"


# ---------------------------------------------------------------------------
# Art panel (left, navy)
# ---------------------------------------------------------------------------

class _ArtPanel(QWidget):
    """Left decorative panel: navy bg + cream symbol overlay + text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(400)

        pix_path = _ASSETS_DIR / "symbol-cream.png"
        self._deco: QPixmap = (
            QPixmap(str(pix_path)) if pix_path.is_file() else QPixmap()
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 48, 56, 48)
        layout.setSpacing(0)

        # ---- Top content ----
        eyebrow = QLabel("Ricardo Passos Advocacia")
        eyebrow.setStyleSheet(
            "color: rgba(237,234,228,0.70);"
            f"font-family: '{FONT_BODY}', sans-serif;"
            "font-size: 10px; font-weight: 700;"
            "letter-spacing: 2px;"
            "background: transparent; border: none;"
        )
        layout.addWidget(eyebrow)

        title = QLabel("Notion RPADV.")
        t_font = QFont(FONT_DISPLAY)
        t_font.setPixelSize(44)
        t_font.setWeight(QFont.Weight(FW_REGULAR))
        title.setFont(t_font)
        title.setStyleSheet(
            "color: #EDEAE4; background: transparent; border: none;"
            "margin-top: 16px;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "Camada enxuta sobre as quatro bases do escritório: "
            "Processos, Clientes, Tarefas e Catálogo. "
            "Sem abrir o Notion."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            "color: rgba(237,234,228,0.78);"
            f"font-family: '{FONT_BODY}', sans-serif;"
            "font-size: 14px;"
            "background: transparent; border: none;"
            "margin-top: 18px;"
        )
        layout.addWidget(desc)

        layout.addStretch(1)

        # ---- Bottom footer ----
        location = QLabel("Brasília · DF · OAB/DF")
        location.setStyleSheet(
            "color: rgba(237,234,228,0.55);"
            f"font-family: '{FONT_BODY}', sans-serif;"
            "font-size: 11px; font-weight: 700;"
            "letter-spacing: 2px;"
            "background: transparent; border: none;"
        )
        layout.addWidget(location)

        version = QLabel("v0.4.2 · build 2026.04")
        v_font = QFont(FONT_MONO)
        v_font.setPixelSize(10)
        version.setFont(v_font)
        version.setStyleSheet(
            "color: rgba(237,234,228,0.70);"
            "background: transparent; border: none;"
        )
        layout.addWidget(version)

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(LIGHT.app_sidebar))

        if not self._deco.isNull():
            target_h = int(self.height() * 1.30)
            scaled = self._deco.scaledToHeight(
                target_h, Qt.TransformationMode.SmoothTransformation
            )
            x = self.width() - scaled.width() + int(self.width() * 0.08)
            y = (self.height() - scaled.height()) // 2
            painter.setOpacity(0.10)
            painter.drawPixmap(x, y, scaled)


# ---------------------------------------------------------------------------
# User pick card
# ---------------------------------------------------------------------------

class _UserPickCard(QPushButton):
    """Selectable user card (avatar + name + role)."""

    def __init__(
        self,
        uid: str,
        name: str,
        initials: str,
        role: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.uid = uid
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(60)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)

        # Avatar circle
        self._avatar = QLabel(initials)
        self._avatar.setFixedSize(QSize(28, 28))
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet(
            f"background-color: {_P.app_accent}; color: #FFFFFF;"
            "border-radius: 14px;"
            f"font-family: '{FONT_BODY}', sans-serif;"
            "font-size: 12px; font-weight: 700;"
            "border: none;"
        )
        row.addWidget(self._avatar)

        info = QVBoxLayout()
        info.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {_P.app_fg};"
            f"font-family: '{FONT_BODY}', sans-serif;"
            f"font-size: {FS_MD}px; font-weight: {FW_SEMIBOLD};"
            "background: transparent; border: none;"
        )
        info.addWidget(name_lbl)

        role_lbl = QLabel(role.upper() if role else "")
        role_lbl.setStyleSheet(
            f"color: {_P.app_fg_subtle};"
            f"font-family: '{FONT_BODY}', sans-serif;"
            "font-size: 10px; font-weight: 600;"
            "letter-spacing: 1px;"
            "background: transparent; border: none;"
        )
        info.addWidget(role_lbl)
        row.addLayout(info)

        self._refresh_style(False)

    def _refresh_style(self, active: bool) -> None:
        if active:
            border_col = _P.app_accent
            bg_col = _P.app_accent_soft
        else:
            border_col = _P.app_border_strong
            bg_col = _P.app_elevated
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg_col};
                border: 1.5px solid {border_col};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border-color: {_P.app_accent};
            }}
            """
        )

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._refresh_style(checked)


# ---------------------------------------------------------------------------
# Form panel (right, cream)
# ---------------------------------------------------------------------------

class _FormPanel(QWidget):
    """Right form panel: user picker + token entry + submit."""

    def __init__(
        self,
        selected_user: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {_P.cream};")

        self._selected_user = selected_user
        self._step = "first-time"
        self._user_cards: dict[str, _UserPickCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        form = QWidget()
        form.setStyleSheet("background: transparent;")
        form.setFixedWidth(360)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(0)
        outer.addWidget(form, alignment=Qt.AlignmentFlag.AlignCenter)

        # ---- Eyebrow + step toggle row ----
        header_row = QHBoxLayout()
        header_row.setSpacing(0)

        self._eyebrow = QLabel("Primeira execução")
        self._eyebrow.setObjectName("Eyebrow")
        self._eyebrow.setStyleSheet(
            f"color: {_P.app_fg_subtle};"
            f"font-family: '{FONT_BODY}', sans-serif;"
            "font-size: 10px; font-weight: 700;"
            "letter-spacing: 2px;"
            "background: transparent; border: none;"
        )
        header_row.addWidget(self._eyebrow)
        header_row.addStretch(1)

        self._toggle_btn = QPushButton("Já configurei")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {_P.app_border};
                border-radius: {RADIUS_MD}px;
                color: {_P.app_fg_muted};
                font-size: 11px;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background: {_P.app_accent_soft};
                border-color: {_P.app_accent};
            }}
            """
        )
        self._toggle_btn.clicked.connect(self._on_toggle_step)
        header_row.addWidget(self._toggle_btn)

        form_layout.addLayout(header_row)
        form_layout.addSpacing(SP_3)

        # ---- H2 ----
        self._heading = QLabel("Configure o acesso ao Notion.")
        h2_font = QFont(FONT_DISPLAY)
        h2_font.setPixelSize(26)
        h2_font.setWeight(QFont.Weight(FW_REGULAR))
        self._heading.setFont(h2_font)
        self._heading.setWordWrap(True)
        self._heading.setStyleSheet(
            f"color: {_P.app_fg_strong}; background: transparent; border: none;"
        )
        form_layout.addWidget(self._heading)
        form_layout.addSpacing(SP_2)

        # ---- Lead text ----
        self._lead = QLabel(
            "O token é guardado no Credential Manager do Windows "
            "e não sai desta máquina."
        )
        self._lead.setWordWrap(True)
        self._lead.setStyleSheet(
            f"color: {_P.app_fg_muted};"
            f"font-family: '{FONT_BODY}', sans-serif;"
            f"font-size: {FS_SM2}px;"
            "background: transparent; border: none;"
        )
        form_layout.addWidget(self._lead)
        form_layout.addSpacing(SP_6)

        # ---- Token field (first-time mode) ----
        token_lbl = QLabel("Token do Notion")
        token_lbl.setStyleSheet(
            f"color: {_P.app_fg_muted};"
            f"font-family: '{FONT_BODY}', sans-serif;"
            f"font-size: {FS_SM}px; font-weight: {FW_MEDIUM};"
            "background: transparent; border: none;"
        )
        form_layout.addWidget(token_lbl)
        form_layout.addSpacing(SP_2)

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setFixedHeight(36)
        self._token_edit.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {_P.app_panel};
                color: {_P.app_fg};
                font-family: '{FONT_BODY}', sans-serif;
                font-size: {FS_MD}px;
                border: 1.5px solid {_P.app_border_strong};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QLineEdit:focus {{
                border-color: {_P.app_accent};
                outline: none;
            }}
            """
        )
        self._token_edit.returnPressed.connect(self._on_submit)
        form_layout.addWidget(self._token_edit)
        form_layout.addSpacing(SP_2)

        # Error label
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        self._error_label.setStyleSheet(
            f"""
            QLabel {{
                color: {_P.app_danger};
                font-family: '{FONT_BODY}', sans-serif;
                font-size: {FS_SM}px;
                background: {_P.app_danger_bg};
                border-radius: {RADIUS_MD}px;
                padding: {SP_2}px {SP_3}px;
                border: none;
            }}
            """
        )
        form_layout.addWidget(self._error_label)
        form_layout.addSpacing(SP_4)

        # ---- User picker ----
        user_lbl = QLabel("Usuário ativo")
        user_lbl.setStyleSheet(
            f"color: {_P.app_fg_muted};"
            f"font-family: '{FONT_BODY}', sans-serif;"
            f"font-size: {FS_SM}px; font-weight: {FW_MEDIUM};"
            "background: transparent; border: none;"
        )
        form_layout.addWidget(user_lbl)
        form_layout.addSpacing(SP_2)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(8)
        for uid, udata in USUARIOS_LOCAIS.items():
            card = _UserPickCard(
                uid,
                udata.get("name", uid),
                udata.get("initials", uid[:2].upper()),
                udata.get("role", ""),
            )
            card.clicked.connect(lambda checked, u=uid: self._select_user(u))
            card.setChecked(uid == self._selected_user)
            self._user_cards[uid] = card
            pick_row.addWidget(card)
        form_layout.addLayout(pick_row)
        form_layout.addSpacing(SP_6)

        # ---- Submit button ----
        self._submit_btn = QPushButton("Validar e entrar")
        self._submit_btn.setFixedHeight(38)
        self._submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._submit_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {_P.app_accent};
                color: {_P.app_accent_fg};
                font-family: '{FONT_BODY}', sans-serif;
                font-size: {FS_MD}px; font-weight: {FW_BOLD};
                border: none;
                border-radius: {RADIUS_MD}px;
            }}
            QPushButton:hover {{ background-color: {_P.app_accent_hover}; }}
            QPushButton:pressed {{ background-color: {_P.navy_dark}; }}
            QPushButton:disabled {{
                background-color: {_P.app_border};
                color: {_P.app_fg_subtle};
            }}
            """
        )
        self._submit_btn.clicked.connect(self._on_submit)
        form_layout.addWidget(self._submit_btn)

        # ---- Token help text ----
        help_lbl = QLabel(
            "Gere em notion.so/my-integrations › New integration "
            "› conceda acesso às 4 bases do escritório."
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet(
            f"color: {_P.app_fg_subtle};"
            f"font-family: '{FONT_BODY}', sans-serif;"
            f"font-size: {FS_SM}px;"
            "background: transparent; border: none;"
            "margin-top: 8px;"
        )
        form_layout.addWidget(help_lbl)

    # ---- Internal state management ----

    def _select_user(self, uid: str) -> None:
        self._selected_user = uid
        for u, card in self._user_cards.items():
            card.setChecked(u == uid)

    def _on_toggle_step(self) -> None:
        if self._step == "first-time":
            self._step = "returning"
            self._eyebrow.setText("Bom dia")
            self._heading.setText("Selecione o usuário ativo.")
            self._lead.setText(
                "O token está armazenado de forma segura. "
                "Escolha quem está usando o computador agora."
            )
            self._toggle_btn.setText("Trocar token")
            self._submit_btn.setText("Entrar")
            self._token_edit.setVisible(False)
        else:
            self._step = "first-time"
            self._eyebrow.setText("Primeira execução")
            self._heading.setText("Configure o acesso ao Notion.")
            self._lead.setText(
                "O token é guardado no Credential Manager do Windows "
                "e não sai desta máquina."
            )
            self._toggle_btn.setText("Já configurei")
            self._submit_btn.setText("Validar e entrar")
            self._token_edit.setVisible(True)
        self._hide_error()

    def _on_submit(self) -> None:
        if self._step == "first-time":
            token = self._token_edit.text().strip()
            if not token:
                self._show_error("Cole o token de integração Notion.")
                return
        else:
            # BUG-13: validate that a stored token actually exists
            from notion_rpadv.auth.token_store import get_token as _get_token
            stored = _get_token()
            if not stored:
                # BUG-N4: button is called 'Trocar token', not 'Primeiro acesso'
                self._show_error(
                    "Nenhum token armazenado. Clique em 'Trocar token' para configurar um novo."
                )
                self._submit_btn.setEnabled(True)
                self._submit_btn.setText("Entrar")
                return
            token = stored

        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("Verificando…" if self._step == "first-time" else "Entrando…")
        self._hide_error()

        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        if self._step == "first-time":
            try:
                client = NotionClient(token)
                client.me()
            except NotionAuthError:
                self._show_error(
                    "Token inválido ou sem permissão. "
                    "Verifique o token de integração Notion."
                )
                self._submit_btn.setEnabled(True)
                self._submit_btn.setText("Validar e entrar")
                return
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"Erro ao conectar: {exc}")
                self._submit_btn.setEnabled(True)
                self._submit_btn.setText("Validar e entrar")
                return

            set_token(token)

        # Signal the parent dialog to accept
        dialog = self.window()
        if isinstance(dialog, QDialog):
            dialog._token_value = token  # type: ignore[attr-defined]
            dialog._selected_user = self._selected_user  # type: ignore[attr-defined]
            dialog.accept()

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.setVisible(True)

    def _hide_error(self) -> None:
        self._error_label.setText("")
        self._error_label.setVisible(False)


# ---------------------------------------------------------------------------
# Main LoginWindow dialog
# ---------------------------------------------------------------------------

class LoginWindow(QDialog):
    """Split-panel login dialog: navy art left + cream form right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Notion RPADV — Entrar")
        self.setFixedSize(860, 560)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._selected_user: str = next(iter(USUARIOS_LOCAIS))
        self._token_value: str = ""

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left: art panel (~53%)
        self._art = _ArtPanel()
        self._art.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._art, stretch=53)

        # Right: form panel (~47%)
        self._form = _FormPanel(self._selected_user)
        self._form.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self._form, stretch=47)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_user(self) -> str:
        return self._selected_user

    def get_token(self) -> str:
        return self._token_value
