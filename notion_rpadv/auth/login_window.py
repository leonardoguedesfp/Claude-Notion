"""Login window shown when no token is stored."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from notion_bulk_edit.config import USUARIOS_LOCAIS
from notion_bulk_edit.notion_api import NotionAuthError, NotionClient
from notion_rpadv.auth.token_store import set_token
from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FONT_DISPLAY,
    FS_LG,
    FS_MD,
    FS_SM,
    FS_SM2,
    FS_XL,
    FW_BOLD,
    FW_MEDIUM,
    FW_REGULAR,
    LIGHT,
    RADIUS_LG,
    RADIUS_MD,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)

_P = LIGHT


class LoginWindow(QDialog):
    """Minimal login dialog: user selects their name and enters the Notion token."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Notion RPADV — Entrar")
        self.setFixedSize(440, 520)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._selected_user: str = next(iter(USUARIOS_LOCAIS))
        self._token_value: str = ""

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_user(self) -> str:
        """Return the selected local user id."""
        return self._selected_user

    def get_token(self) -> str:
        """Return the entered Notion integration token."""
        return self._token_value

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Outer background
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {_P.cream};
            }}
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Card frame centered
        card = QFrame(self)
        card.setFixedWidth(380)
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {_P.app_panel};
                border-radius: {RADIUS_LG}px;
                border: 1px solid {_P.app_border};
            }}
            """
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(SP_8, SP_8, SP_8, SP_8)
        card_layout.setSpacing(SP_4)

        # --- Logo / header ---
        logo_row = QHBoxLayout()
        logo_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rp_label = QLabel("RP")
        rp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rp_font = QFont(FONT_DISPLAY)
        rp_font.setPixelSize(36)
        rp_font.setWeight(QFont.Weight(FW_BOLD))
        rp_label.setFont(rp_font)
        rp_label.setStyleSheet(
            f"color: {_P.navy_base}; background: transparent; border: none;"
        )
        logo_row.addWidget(rp_label)
        card_layout.addLayout(logo_row)

        firm_label = QLabel("RPADV ADVOCACIA")
        firm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        firm_label.setStyleSheet(
            f"""
            QLabel {{
                color: {_P.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                letter-spacing: 3px;
                background: transparent;
                border: none;
            }}
            """
        )
        card_layout.addWidget(firm_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(
            f"background-color: {_P.app_divider}; border: none;"
        )
        card_layout.addWidget(sep)
        card_layout.addSpacing(SP_2)

        # --- Heading ---
        heading = QLabel("Bem-vindo")
        heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color: {_P.navy_base}; background: transparent; border: none;"
        )
        card_layout.addWidget(heading)

        sub = QLabel("Selecione seu nome e cole o token de integração Notion.")
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"""
            QLabel {{
                color: {_P.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_REGULAR};
                background: transparent;
                border: none;
            }}
            """
        )
        card_layout.addWidget(sub)
        card_layout.addSpacing(SP_2)

        # --- User dropdown ---
        user_lbl = self._make_field_label("Usuário")
        card_layout.addWidget(user_lbl)

        self._user_combo = QComboBox()
        self._user_combo.setFixedHeight(36)
        self._style_input(self._user_combo)
        for uid, udata in USUARIOS_LOCAIS.items():
            self._user_combo.addItem(udata["name"], userData=uid)
        self._user_combo.currentIndexChanged.connect(self._on_user_changed)
        card_layout.addWidget(self._user_combo)

        # --- Token field ---
        token_lbl = self._make_field_label("Token de Integração Notion")
        card_layout.addWidget(token_lbl)

        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("secret_…")
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setFixedHeight(36)
        self._style_input(self._token_edit)
        self._token_edit.returnPressed.connect(self._on_login)
        card_layout.addWidget(self._token_edit)

        # --- Error label ---
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        self._error_label.setStyleSheet(
            f"""
            QLabel {{
                color: {_P.app_danger};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                background: {_P.app_danger_bg};
                border-radius: {RADIUS_MD}px;
                padding: {SP_2}px {SP_3}px;
                border: none;
            }}
            """
        )
        card_layout.addWidget(self._error_label)
        card_layout.addSpacing(SP_2)

        # --- Login button ---
        self._login_btn = QPushButton("Entrar")
        self._login_btn.setFixedHeight(40)
        self._login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {_P.app_accent};
                color: {_P.app_accent_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                font-weight: {FW_BOLD};
                border: none;
                border-radius: {RADIUS_MD}px;
            }}
            QPushButton:hover {{
                background-color: {_P.app_accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {_P.navy_dark};
            }}
            QPushButton:disabled {{
                background-color: {_P.app_border};
                color: {_P.app_fg_subtle};
            }}
            """
        )
        self._login_btn.clicked.connect(self._on_login)
        card_layout.addWidget(self._login_btn)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {_P.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        return lbl

    def _style_input(self, widget: QWidget) -> None:
        widget.setStyleSheet(
            f"""
            QComboBox, QLineEdit {{
                background-color: {_P.app_bg};
                color: {_P.app_fg};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                border: 1px solid {_P.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QComboBox:focus, QLineEdit:focus {{
                border-color: {_P.app_accent};
                outline: none;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            """
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_user_changed(self, index: int) -> None:
        uid = self._user_combo.itemData(index)
        if uid is not None:
            self._selected_user = str(uid)

    def _on_login(self) -> None:
        token = self._token_edit.text().strip()
        if not token:
            self._show_error("Cole o token de integração Notion.")
            return

        self._login_btn.setEnabled(False)
        self._login_btn.setText("Verificando…")
        self._hide_error()

        # Force UI repaint before blocking call
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            client = NotionClient(token)
            client.me()
        except NotionAuthError:
            self._show_error(
                "Token inválido ou sem permissão. Verifique o token de integração Notion."
            )
            self._login_btn.setEnabled(True)
            self._login_btn.setText("Entrar")
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"Erro ao conectar: {exc}")
            self._login_btn.setEnabled(True)
            self._login_btn.setText("Entrar")
            return

        set_token(token)
        self._token_value = token
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _hide_error(self) -> None:
        self._error_label.setVisible(False)
        self._error_label.setText("")
