"""§9 EmptyState widget — shown when a base has zero records after sync."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from notion_rpadv.theme.tokens import (
    DARK,
    FONT_BODY,
    FONT_DISPLAY,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    LIGHT,
    Palette,
    RADIUS_MD,
    RADIUS_XL,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)


class EmptyState(QWidget):
    """§9 Full-area empty state for a base with no records.

    Parameters
    ----------
    base_name:
        Human-readable name of the base, e.g. "Processos".
    on_sync:
        Callback for the primary "Sincronizar agora" button.
    on_create:
        Optional callback for the secondary "Criar primeiro registro" button.
    last_sync_text:
        Short text shown in footer, e.g. "há 1 min · 0 registros · sem erros".
    dark:
        Whether to use the dark palette.
    """

    def __init__(
        self,
        base_name: str = "",
        on_sync: Callable[[], None] | None = None,
        on_create: Callable[[], None] | None = None,
        last_sync_text: str = "",
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_name = base_name
        self._on_sync = on_sync
        self._on_create = on_create
        self._last_sync_text = last_sync_text
        self._p: Palette = DARK if dark else LIGHT
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_last_sync_text(self, text: str) -> None:
        """Update the footer sync status text."""
        self._footer_lbl.setText(text)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SP_8, SP_8, SP_8, SP_8)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Center card
        card = QFrame()
        card.setObjectName("EmptyStateCard")
        card.setFixedWidth(480)
        card.setStyleSheet(
            f"""
            QFrame#EmptyStateCard {{
                background-color: {p.app_panel};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_XL}px;
            }}
            """
        )
        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(SP_8, SP_6, SP_8, SP_6)
        layout.setSpacing(SP_4)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Icon circle
        icon_circle = QLabel("📥")
        icon_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_circle.setFixedSize(64, 64)
        icon_circle.setStyleSheet(
            f"""
            QLabel {{
                font-size: 28px;
                background-color: {p.app_row_hover};
                border-radius: 32px;
                border: none;
            }}
            """
        )
        layout.addWidget(icon_circle, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Title
        base_part = f" em {self._base_name}" if self._base_name else ""
        title = QLabel(f"Nenhum registro{base_part} ainda")
        title_font = QFont(FONT_DISPLAY)
        title_font.setPixelSize(20)
        title_font.setWeight(QFont.Weight(FW_BOLD))
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;"
        )
        layout.addWidget(title)

        # Sub-text
        sub = QLabel(
            "A última sincronização não retornou registros.\n"
            "Isso pode ser normal se a base estiver vazia no Notion."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_fg_muted};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_MD}px;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(sub)

        layout.addSpacing(SP_2)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SP_3)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        sync_btn = QPushButton("Sincronizar agora")
        sync_btn.setFixedHeight(36)
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.setStyleSheet(
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
            QPushButton:hover {{ background-color: {p.app_accent_hover}; }}
            """
        )
        if self._on_sync:
            sync_btn.clicked.connect(self._on_sync)
        btn_row.addWidget(sync_btn)

        if self._on_create:
            create_btn = QPushButton("Criar primeiro registro")
            create_btn.setFixedHeight(36)
            create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            create_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: transparent;
                    color: {p.app_fg};
                    font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                    font-size: {FS_SM2}px;
                    font-weight: {FW_MEDIUM};
                    border: 1px solid {p.app_border_strong};
                    border-radius: {RADIUS_MD}px;
                    padding: 0 {SP_4}px;
                }}
                QPushButton:hover {{ background-color: {p.app_row_hover}; }}
                """
            )
            create_btn.clicked.connect(self._on_create)
            btn_row.addWidget(create_btn)

        layout.addLayout(btn_row)

        # Footer divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {p.app_divider}; border: none;")
        layout.addWidget(div)

        # Footer sync status
        footer_text = self._last_sync_text or "Última sync: —"
        self._footer_lbl = QLabel(footer_text)
        self._footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_fg_subtle};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(self._footer_lbl)
