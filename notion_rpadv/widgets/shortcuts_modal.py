"""Keyboard shortcuts reference modal."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QWidget,
    QFrame,
    QScrollArea,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent

from notion_rpadv.services.shortcuts import DEFAULT_SHORTCUTS
from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FONT_MONO,
    FS_SM,
    FS_SM2,
    FS_MD,
    FS_LG,
    FW_BOLD,
    FW_MEDIUM,
    SP_1,
    SP_2,
    SP_3,
    SP_4,
    RADIUS_LG,
    RADIUS_XL,
    RADIUS_MD,
)

# Maps action key → human-readable Portuguese label
_ACTION_LABELS: dict[str, str] = {
    "search":        "Abrir paleta de comandos",
    "new_record":    "Novo registro",
    "save":          "Salvar alterações",
    "discard":       "Descartar / Fechar",
    "refresh":       "Atualizar dados",
    "toggle_theme":  "Alternar tema claro / escuro",
    "nav_processos": "Ir para Processos",
    "nav_clientes":  "Ir para Clientes",
    "nav_tarefas":   "Ir para Tarefas",
    "nav_catalogo":  "Ir para Catálogo",
}

# Maps action key → section name (for grouping)
_ACTION_SECTIONS: dict[str, str] = {
    "search":        "Geral",
    "new_record":    "Geral",
    "save":          "Geral",
    "discard":       "Geral",
    "refresh":       "Geral",
    "toggle_theme":  "Aparência",
    "nav_processos": "Navegação",
    "nav_clientes":  "Navegação",
    "nav_tarefas":   "Navegação",
    "nav_catalogo":  "Navegação",
}


def _kbd_badge(key: str) -> QLabel:
    """Render a keyboard key as a styled Kbd badge label."""
    lbl = QLabel(key)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedHeight(22)
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    lbl.setStyleSheet(
        f"""
        QLabel {{
            background-color: #F0EDE7;
            color: #3F4751;
            font-family: "{FONT_MONO}", "Consolas", "Courier New", monospace;
            font-size: {FS_SM2}px;
            font-weight: {FW_MEDIUM};
            border: 1px solid #CAD5DD;
            border-bottom: 2px solid #9FB3C1;
            border-radius: {RADIUS_MD}px;
            padding: 0 {SP_2}px;
        }}
        """
    )
    return lbl


def _section_header(title: str) -> QLabel:
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"""
        QLabel {{
            color: #9FB3C1;
            font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
            font-size: {FS_SM}px;
            font-weight: {FW_BOLD};
            letter-spacing: 1px;
            background: transparent;
            border: none;
            padding-top: {SP_3}px;
            padding-bottom: {SP_1}px;
        }}
        """
    )
    return lbl


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: rgba(20,36,48,0.08); border: none;")
    return line


class _ModalCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ShortcutsCard")
        self.setStyleSheet(
            f"""
            QFrame#ShortcutsCard {{
                background-color: #FFFFFF;
                border-radius: {RADIUS_XL}px;
                border: 1px solid rgba(20,36,48,0.10);
            }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(10, 15, 20, 60))
        self.setGraphicsEffect(shadow)


class ShortcutsModal(QDialog):
    """Shows all keyboard shortcuts in a grouped grid.

    Parameters
    ----------
    bindings:
        Mapping of action key → key-sequence string, e.g.
        ``{"save": "Ctrl+S", "search": "Ctrl+K"}``.  Defaults to
        :data:`~notion_rpadv.services.shortcuts.DEFAULT_SHORTCUTS` if an
        empty dict is passed.
    parent:
        Parent widget (main window).

    Usage::

        dlg = ShortcutsModal(bindings=registry.get_bindings(), parent=self)
        dlg.exec()
    """

    def __init__(
        self,
        bindings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(520)

        effective_bindings: dict[str, str] = bindings if bindings else dict(DEFAULT_SHORTCUTS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = _ModalCard()
        self._card.setFixedWidth(500)
        outer.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(SP_4, SP_4, SP_4, SP_4)
        card_layout.setSpacing(SP_2)

        # --- Title row ---
        title_row = QHBoxLayout()
        title_lbl = QLabel("Atalhos de Teclado")
        title_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: #0A0F14;
                font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif;
                font-size: 18px;
                font-weight: {FW_BOLD};
                background: transparent;
                border: none;
            }}
            """
        )
        title_row.addWidget(title_lbl, stretch=1)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                color: rgba(20,36,48,0.55);
                font-size: 18px;
                background: transparent;
                border: none;
                border-radius: {RADIUS_MD}px;
            }}
            QPushButton:hover {{
                background-color: rgba(20,36,48,0.06);
                color: rgba(20,36,48,0.85);
            }}
            """
        )
        close_btn.clicked.connect(self.accept)
        title_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(title_row)

        card_layout.addWidget(_divider())

        # --- Scrollable content ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, SP_2, 0)
        content_layout.setSpacing(0)

        # Group actions by section
        sections: dict[str, list[tuple[str, str]]] = {}
        for action, key_seq in effective_bindings.items():
            section = _ACTION_SECTIONS.get(action, "Outros")
            label = _ACTION_LABELS.get(action, action.replace("_", " ").title())
            sections.setdefault(section, []).append((label, key_seq))

        for section_name, entries in sections.items():
            content_layout.addWidget(_section_header(section_name))

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, SP_2)
            grid.setSpacing(SP_2)
            grid.setColumnStretch(0, 1)

            for row_idx, (action_label, key_seq) in enumerate(entries):
                # Action label
                action_lbl = QLabel(action_label)
                action_lbl.setStyleSheet(
                    f"""
                    QLabel {{
                        color: #3F4751;
                        font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                        font-size: {FS_MD}px;
                        font-weight: {FW_MEDIUM};
                        background: transparent;
                        border: none;
                    }}
                    """
                )
                grid.addWidget(action_lbl, row_idx, 0, Qt.AlignmentFlag.AlignVCenter)

                # Key badge(s) — split composite shortcuts like "Ctrl+Shift+T"
                # into individual key tokens separated by "+"
                badges_widget = QWidget()
                badges_widget.setStyleSheet("background: transparent;")
                badges_layout = QHBoxLayout(badges_widget)
                badges_layout.setContentsMargins(0, 0, 0, 0)
                badges_layout.setSpacing(SP_1)

                tokens = _split_shortcut(key_seq)
                for i, token in enumerate(tokens):
                    badges_layout.addWidget(_kbd_badge(token))
                    if i < len(tokens) - 1:
                        plus = QLabel("+")
                        plus.setStyleSheet(
                            f"color: #9FB3C1; font-size: {FS_SM}px; background: transparent; border: none;"
                        )
                        badges_layout.addWidget(plus)

                badges_layout.addStretch()
                grid.addWidget(badges_widget, row_idx, 1, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

            content_layout.addLayout(grid)

        content_layout.addStretch()
        scroll.setWidget(content)
        scroll.setMaximumHeight(400)
        card_layout.addWidget(scroll)

        card_layout.addWidget(_divider())

        # --- Footer close button ---
        footer = QHBoxLayout()
        footer.setContentsMargins(0, SP_1, 0, 0)
        footer.addStretch()
        ok_btn = QPushButton("Fechar")
        ok_btn.setFixedHeight(32)
        ok_btn.setMinimumWidth(80)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #FFFFFF;
                color: #3F4751;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: 1px solid #CAD5DD;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{
                background-color: #F5F7F9;
            }}
            """
        )
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(ok_btn)
        card_layout.addLayout(footer)

    # ------------------------------------------------------------------
    # Paint backdrop
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 15, 20, 115))
        painter.end()


def _split_shortcut(sequence: str) -> list[str]:
    """Split a key sequence string into displayable token parts.

    Examples::

        "Ctrl+S"         → ["Ctrl", "S"]
        "Ctrl+Shift+T"   → ["Ctrl", "Shift", "T"]
        "F5"             → ["F5"]
        "Escape"         → ["Esc"]
    """
    _ALIASES: dict[str, str] = {
        "Escape": "Esc",
        "Return": "Enter",
        "Delete": "Del",
        "Backspace": "⌫",
        "Control": "Ctrl",
        "Meta": "⌘",
        "Alt": "Alt",
    }
    if not sequence:
        return [sequence]
    parts = sequence.split("+")
    return [_ALIASES.get(p, p) for p in parts if p]
