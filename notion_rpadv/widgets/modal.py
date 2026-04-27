"""Base modal dialog widget."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QWidget,
    QFrame,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QPainter, QPaintEvent

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FS_MD,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    SP_2,
    SP_3,
    SP_4,
    RADIUS_XL,
    RADIUS_MD,
)

_BACKDROP_COLOR = "rgba(10,15,20,0.45)"

# Button role → (bg, fg, hover_bg, border)
_BTN_STYLES: dict[str, tuple[str, str, str, str]] = {
    "primary":   ("#104063", "#FFFFFF", "#0C324D", "transparent"),
    "secondary": ("#FFFFFF",  "#142430", "#F5F7F9", "#CAD5DD"),
    "danger":    ("#9A3B3B",  "#FFFFFF", "#7A2E2E", "transparent"),
}


def _make_button(label: str, role: str) -> QPushButton:
    bg, fg, hover_bg, border = _BTN_STYLES.get(role, _BTN_STYLES["secondary"])
    border_style = (
        f"1px solid {border}" if border != "transparent" else "none"
    )
    btn = QPushButton(label)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(34)
    btn.setMinimumWidth(90)
    btn.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
            font-size: {FS_SM2}px;
            font-weight: {FW_MEDIUM};
            border: {border_style};
            border-radius: {RADIUS_MD}px;
            padding: 0 {SP_4}px;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
        }}
        QPushButton:pressed {{
            opacity: 0.85;
        }}
        """
    )
    return btn


class _ModalCard(QFrame):
    """Inner white card inside the transparent dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModalCard")
        self.setStyleSheet(
            f"""
            QFrame#ModalCard {{
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


class Modal(QDialog):
    """Centered modal with title, content area, and footer buttons.

    Usage::

        dlg = Modal("Editar Processo", parent=self)
        dlg.set_content(my_form_widget)
        ok_btn = dlg.add_button("Salvar", role="primary")
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = dlg.add_button("Cancelar")
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()

    The dialog renders a semi-transparent backdrop and a white rounded card.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(480)

        # Full-screen transparent backdrop
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = _ModalCard()
        self._card.setMinimumWidth(440)
        self._card.setMaximumWidth(640)
        outer.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(SP_4, SP_4, SP_4, SP_3)
        card_layout.setSpacing(SP_3)

        # --- Title row ---
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
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
        title_row.addWidget(self._title_lbl, stretch=1)

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
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)

        card_layout.addLayout(title_row)

        # --- Divider ---
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(20,36,48,0.08); border: none;")
        card_layout.addWidget(divider)

        # --- Content placeholder ---
        self._content_widget: QWidget | None = None
        self._content_slot = QVBoxLayout()
        self._content_slot.setContentsMargins(0, 0, 0, 0)
        card_layout.addLayout(self._content_slot)

        # --- Footer ---
        self._footer = QHBoxLayout()
        self._footer.setContentsMargins(0, SP_2, 0, 0)
        self._footer.setSpacing(SP_2)
        self._footer.addStretch()
        card_layout.addLayout(self._footer)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_content(self, widget: QWidget) -> None:
        """Place *widget* into the content area (replaces any previous one)."""
        if self._content_widget is not None:
            self._content_slot.removeWidget(self._content_widget)
            self._content_widget.setParent(None)  # type: ignore[call-overload]
        self._content_widget = widget
        self._content_slot.addWidget(widget)

    def add_button(self, label: str, role: str = "secondary") -> QPushButton:
        """Append a footer button and return it so callers can connect signals."""
        btn = _make_button(label, role)
        self._footer.addWidget(btn)
        return btn

    # ------------------------------------------------------------------
    # Paint backdrop
    # ------------------------------------------------------------------

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        # BUG-N16: size the dialog to cover the parent window so backdrop works
        pw = self.parent()
        if pw and hasattr(pw, "width"):
            self.resize(pw.width(), pw.height())  # type: ignore[union-attr]
            self.move(pw.mapToGlobal(QPoint(0, 0)))  # type: ignore[union-attr]
        super().showEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 15, 20, 115))
        painter.end()


class ConfirmModal(Modal):
    """Simple yes/no confirmation dialog.

    Usage::

        dlg = ConfirmModal(
            "Excluir processo",
            "Esta ação não pode ser desfeita.",
            confirm_label="Excluir",
            danger=True,
            parent=self,
        )
        if dlg.exec_and_get():
            ...  # user confirmed
    """

    def __init__(
        self,
        title: str,
        message: str,
        confirm_label: str = "Confirmar",
        danger: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)

        # Message content
        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
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
        self.set_content(msg_lbl)

        # Footer buttons — cancel always first, confirm second
        cancel_btn = self.add_button("Cancelar", role="secondary")
        cancel_btn.clicked.connect(self.reject)

        role = "danger" if danger else "primary"
        confirm_btn = self.add_button(confirm_label, role=role)
        confirm_btn.clicked.connect(self.accept)

    def exec_and_get(self) -> bool:
        """Execute the dialog modally and return ``True`` if the user confirmed."""
        return self.exec() == QDialog.DialogCode.Accepted
