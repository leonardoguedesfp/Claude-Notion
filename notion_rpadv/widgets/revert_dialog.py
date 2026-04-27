"""§6.2 RevertDialog — ApplicationModal confirmation for log revert with diff table."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FONT_DISPLAY,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    RADIUS_MD,
    RADIUS_XL,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
)


class RevertDialog(QDialog):
    """§6.2 ApplicationModal revert confirmation with diff table.

    Shows: eyebrow, title, summary, diff (before/after), disclaimer,
    and Cancel / Confirmar reversão buttons.

    Usage::

        dlg = RevertDialog(entry, parent=window)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ...
    """

    def __init__(self, entry: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # §6.2 must cover whole app, not just the parent widget
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(480)

        self._entry = entry
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        entry = self._entry

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("RevertCard")
        card.setFixedWidth(480)
        card.setStyleSheet(
            f"""
            QFrame#RevertCard {{
                background-color: #FFFFFF;
                border-radius: {RADIUS_XL}px;
                border: 1px solid rgba(20,36,48,0.10);
            }}
            """
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(10, 15, 20, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(SP_6, SP_6, SP_6, SP_4)
        layout.setSpacing(SP_3)

        # Eyebrow
        eyebrow = QLabel("CONFIRMAÇÃO DESTRUTIVA")
        eyebrow.setStyleSheet(
            f"""
            QLabel {{
                color: #9A3B3B;
                font-family: "{FONT_BODY}", sans-serif;
                font-size: 10px;
                font-weight: {FW_BOLD};
                letter-spacing: 1.5px;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(eyebrow)

        # Title
        title = QLabel("Reverter alteração?")
        title_font = QFont(FONT_DISPLAY)
        title_font.setPixelSize(20)
        title_font.setWeight(QFont.Weight(FW_BOLD))
        title.setFont(title_font)
        title.setStyleSheet("color: #0A0F14; background: transparent; border: none;")
        layout.addWidget(title)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet("background-color: rgba(20,36,48,0.08); border: none;")
        layout.addWidget(div)

        # Summary
        user = entry.get("user", "—")
        base = entry.get("base", "—")
        applied_at = float(entry.get("applied_at", 0))
        if applied_at:
            dt_str = datetime.fromtimestamp(applied_at).strftime("%d/%m %H:%M")
        else:
            dt_str = "—"
        key = entry.get("key", "—")

        summary = QLabel(
            f"Reverter alteração feita por <b>{user}</b> em <b>{dt_str}</b>:"
            f"<br>Campo <i>{key}</i> na base {base}"
        )
        summary.setWordWrap(True)
        summary.setStyleSheet(
            f"""
            QLabel {{
                color: #3F4751;
                font-family: "{FONT_BODY}", sans-serif;
                font-size: {FS_MD}px;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(summary)

        # Diff table
        diff_table = QTableWidget(1, 2)
        diff_table.setHorizontalHeaderLabels(["Antes", "Depois"])
        diff_table.verticalHeader().setVisible(False)
        diff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        diff_table.setShowGrid(True)
        diff_table.setFixedHeight(62)
        diff_table.horizontalHeader().setStretchLastSection(True)
        diff_table.setStyleSheet(
            f"""
            QTableWidget {{
                background: #FAFAFA;
                border: 1px solid rgba(20,36,48,0.10);
                border-radius: {RADIUS_MD}px;
                font-size: {FS_SM2}px;
            }}
            QHeaderView::section {{
                background: #F5F7F9;
                font-size: 10px;
                font-weight: {FW_BOLD};
                letter-spacing: 1px;
                color: #6F6B68;
                border: none;
                border-bottom: 1px solid rgba(20,36,48,0.08);
                padding: 4px 8px;
            }}
            """
        )

        old_val = self._fmt_value(entry.get("old_value"))
        new_val = self._fmt_value(entry.get("new_value"))

        old_item = QTableWidgetItem(old_val)
        old_item.setForeground(QColor("#9A3B3B"))
        old_item.setFlags(old_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        diff_table.setItem(0, 0, old_item)

        new_item = QTableWidgetItem(new_val)
        new_item.setForeground(QColor("#3F6E55"))
        new_item.setFlags(new_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        diff_table.setItem(0, 1, new_item)

        layout.addWidget(diff_table)

        # Disclaimer
        disclaimer = QLabel(
            "A alteração será desfeita no Notion e registrada como evento 'Reversão'."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(
            f"""
            QLabel {{
                color: #9FB3C1;
                font-family: "{FONT_BODY}", sans-serif;
                font-size: {FS_SM}px;
                background: transparent;
                border: none;
            }}
            """
        )
        layout.addWidget(disclaimer)

        # Footer buttons
        footer = QHBoxLayout()
        footer.setContentsMargins(0, SP_2, 0, 0)
        footer.setSpacing(SP_2)

        cancel_btn = self._make_btn("Cancelar", primary=False)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        footer.addStretch()

        confirm_btn = self._make_btn("Confirmar reversão", primary=True, danger=True)
        confirm_btn.clicked.connect(self.accept)
        footer.addWidget(confirm_btn)

        layout.addLayout(footer)

    # ------------------------------------------------------------------
    # Backdrop
    # ------------------------------------------------------------------

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        pw = self.parent()
        if pw and hasattr(pw, "width"):
            self.resize(pw.width(), pw.height())  # type: ignore[union-attr]
        super().showEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 15, 20, 115))
        painter.end()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_value(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    @staticmethod
    def _make_btn(text: str, primary: bool = False, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(34)
        btn.setMinimumWidth(90)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if danger:
            bg, fg, hbg = "#9A3B3B", "#FFFFFF", "#7A2E2E"
            border = "none"
        elif primary:
            bg, fg, hbg = "#104063", "#FFFFFF", "#0C324D"
            border = "none"
        else:
            bg, fg, hbg = "transparent", "#142430", "#F5F7F9"
            border = "1px solid #CAD5DD"
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                font-family: "{FONT_BODY}", sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                border: {border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{ background-color: {hbg}; }}
            """
        )
        return btn
