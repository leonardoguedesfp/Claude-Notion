"""Item delegates for inline editing in the table."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QDate, QModelIndex, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QLineEdit,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QWidget,
    QApplication,
)

from notion_bulk_edit.config import NOTION_USERS
from notion_bulk_edit.schemas import PropSpec, get_prop

# Types that cannot be edited via a delegate.
# BUG-N11: 'people' removed — has a simple combo editor now.
# 'relation' remains non-editable until a proper picker is built.
_NON_EDITABLE_TIPOS = frozenset(
    {
        "rollup",
        "formula",
        "relation",
        "created_time",
        "last_edited_time",
        "created_by",
        "last_edited_by",
        "files",
    }
)

# BUG-N11: people editor options derived from NOTION_USERS
_PEOPLE_OPTIONS: list[tuple[str, str]] = [
    (uid, info.get("name", uid)) for uid, info in NOTION_USERS.items()
]

# Fallback chip colour when cor_por_valor has no match.
_CHIP_DEFAULT_BG = QColor("#E0E0E0")
_CHIP_DEFAULT_FG = QColor("#212121")
_CHIP_PADDING_H = 6
_CHIP_PADDING_V = 2
_CHIP_RADIUS = 10
_CHIP_GAP = 4


def _parse_color(hex_color: str) -> QColor:
    """Parse a hex color string, return a default if invalid."""
    c = QColor(hex_color)
    return c if c.isValid() else _CHIP_DEFAULT_BG


def _contrasting_text_color(bg: QColor) -> QColor:
    """Return black or white based on background luminance."""
    luminance = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    return QColor("#111111") if luminance > 128 else QColor("#FAFAFA")


def _get_spec_from_index(index: QModelIndex) -> PropSpec | None:
    """Retrieve the PropSpec for the column represented by *index*."""
    model = index.model()
    # Support proxy models.
    while hasattr(model, "sourceModel"):
        model = model.sourceModel()  # type: ignore[union-attr]
    base: str | None = getattr(model, "_base", None)
    cols: list[str] | None = getattr(model, "_cols", None)
    if base is None or cols is None:
        return None
    col_idx = index.column()
    # When coming through a proxy, the column may already be mapped.
    if col_idx < 0 or col_idx >= len(cols):
        return None
    key = cols[col_idx]
    return get_prop(base, key)


class PropDelegate(QStyledItemDelegate):
    """Universal delegate — creates the right editor widget based on PropSpec.tipo."""

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QWidget | None:
        spec = _get_spec_from_index(index)
        if spec is None:
            return None
        if spec.tipo in _NON_EDITABLE_TIPOS:
            return None

        tipo = spec.tipo

        if tipo == "select":
            combo = QComboBox(parent)
            combo.addItem("")  # allow clearing
            for opt in (spec.opcoes or []):
                combo.addItem(opt)
            return combo

        if tipo == "multi_select":
            # Simple comma-separated text editor for multi-select.
            # A full multi-select widget would be a custom popup; QLineEdit is
            # sufficient for the current iteration.
            editor = QLineEdit(parent)
            editor.setPlaceholderText("Comma-separated values…")
            return editor

        if tipo == "date":
            de = QDateEdit(parent)
            de.setCalendarPopup(True)
            de.setDisplayFormat("dd/MM/yyyy")
            return de

        if tipo == "checkbox":
            cb = QCheckBox(parent)
            return cb

        if tipo in (
            "number",
            "rich_text",
            "email",
            "phone_number",
            "url",
        ):
            le = QLineEdit(parent)
            return le

        if tipo == "title":
            le = QLineEdit(parent)
            font = le.font()
            font.setBold(True)
            le.setFont(font)
            return le

        # BUG-N11: simple combo editor for people fields
        if tipo == "people":
            combo = QComboBox(parent)
            combo.addItem("(nenhum)", None)
            for uid, name in _PEOPLE_OPTIONS:
                combo.addItem(name, uid)
            return combo

        return None

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        spec = _get_spec_from_index(index)
        if spec is None:
            return

        raw: Any = index.data(Qt.ItemDataRole.EditRole)
        tipo = spec.tipo

        if tipo == "select" and isinstance(editor, QComboBox):
            val = str(raw) if raw is not None else ""
            idx = editor.findText(val)
            # BUG-N17: if value not in options (legacy), add it to avoid silent data loss
            if idx < 0 and val:
                editor.addItem(f"{val} (legado)", val)
                idx = editor.count() - 1
            editor.setCurrentIndex(idx if idx >= 0 else 0)
            return

        if tipo == "people" and isinstance(editor, QComboBox):
            # raw is a list of user IDs; show first user in the combo
            first_uid = raw[0] if isinstance(raw, list) and raw else (raw or None)
            idx = editor.findData(first_uid) if first_uid else 0
            editor.setCurrentIndex(idx if idx >= 0 else 0)
            return

        if tipo == "multi_select" and isinstance(editor, QLineEdit):
            if isinstance(raw, list):
                editor.setText(", ".join(str(v) for v in raw))
            elif raw is not None:
                editor.setText(str(raw))
            else:
                editor.setText("")
            return

        if tipo == "date" and isinstance(editor, QDateEdit):
            if raw:
                try:
                    # raw is expected as "YYYY-MM-DD".
                    date = QDate.fromString(str(raw)[:10], "yyyy-MM-dd")
                    if date.isValid():
                        editor.setDate(date)
                        return
                except Exception:  # noqa: BLE001
                    pass
            editor.setDate(QDate.currentDate())
            return

        if tipo == "checkbox" and isinstance(editor, QCheckBox):
            editor.setChecked(bool(raw))
            return

        if isinstance(editor, QLineEdit):
            editor.setText(str(raw) if raw is not None else "")
            return

        super().setEditorData(editor, index)

    def setModelData(
        self,
        editor: QWidget,
        model: Any,
        index: QModelIndex,
    ) -> None:
        spec = _get_spec_from_index(index)
        if spec is None:
            return

        tipo = spec.tipo

        if tipo == "select" and isinstance(editor, QComboBox):
            # Use userData if set (for legacy items), otherwise currentText
            value: Any = editor.currentData() if editor.currentData() is not None else editor.currentText() or None
            model.setData(index, value, Qt.ItemDataRole.EditRole)
            return

        if tipo == "people" and isinstance(editor, QComboBox):
            uid = editor.currentData()
            value = [uid] if uid else []
            model.setData(index, value, Qt.ItemDataRole.EditRole)
            return

        if tipo == "multi_select" and isinstance(editor, QLineEdit):
            text = editor.text().strip()
            if text:
                value = [v.strip() for v in text.split(",") if v.strip()]
            else:
                value = []
            model.setData(index, value, Qt.ItemDataRole.EditRole)
            return

        if tipo == "date" and isinstance(editor, QDateEdit):
            date = editor.date()
            value = date.toString("yyyy-MM-dd") if date.isValid() else None
            model.setData(index, value, Qt.ItemDataRole.EditRole)
            return

        if tipo == "checkbox" and isinstance(editor, QCheckBox):
            model.setData(index, editor.isChecked(), Qt.ItemDataRole.EditRole)
            return

        if isinstance(editor, QLineEdit):
            text = editor.text()
            if tipo == "number":
                try:
                    num: Any = float(text) if "." in text else int(text)
                    model.setData(index, num, Qt.ItemDataRole.EditRole)
                except (ValueError, TypeError):
                    model.setData(index, text or None, Qt.ItemDataRole.EditRole)
            else:
                model.setData(index, text or None, Qt.ItemDataRole.EditRole)
            return

        super().setModelData(editor, model, index)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        spec = _get_spec_from_index(index)

        # For select / multi_select, draw chip-style pills.
        if spec is not None and spec.tipo in ("select", "multi_select"):
            raw: Any = index.data(Qt.ItemDataRole.DisplayRole)
            values: list[str]
            if spec.tipo == "multi_select":
                if isinstance(raw, str) and raw:
                    values = [v.strip() for v in raw.split(",") if v.strip()]
                elif isinstance(raw, list):
                    values = [str(v) for v in raw]
                else:
                    values = []
            else:
                values = [str(raw)] if raw else []

            # Draw background first (selection, alternating, dirty).
            super().paint(painter, option, index)

            if not values:
                return

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            rect = option.rect
            x = rect.x() + _CHIP_PADDING_H
            y = rect.y() + (rect.height() - 20) // 2  # vertically centred

            cor_map: dict[str, str] = spec.cor_por_valor or {}

            font = QApplication.font()
            font.setPointSize(8)
            painter.setFont(font)
            fm = painter.fontMetrics()

            for chip_text in values:
                if x >= rect.right() - _CHIP_PADDING_H:
                    break  # no more space

                hex_color = cor_map.get(chip_text, "")
                bg = _parse_color(hex_color) if hex_color else _CHIP_DEFAULT_BG
                fg = _contrasting_text_color(bg)

                text_w = fm.horizontalAdvance(chip_text)
                chip_w = text_w + _CHIP_PADDING_H * 2
                chip_h = fm.height() + _CHIP_PADDING_V * 2

                chip_rect_right = min(x + chip_w, rect.right() - _CHIP_PADDING_H)
                actual_chip_w = chip_rect_right - x

                painter.setBrush(QBrush(bg))
                painter.setPen(Qt.PenStyle.NoPen)
                from PySide6.QtCore import QRectF
                painter.drawRoundedRect(
                    QRectF(x, y, actual_chip_w, chip_h), _CHIP_RADIUS, _CHIP_RADIUS
                )

                painter.setPen(QPen(fg))
                from PySide6.QtCore import QRect as _QRect
                painter.drawText(
                    _QRect(x + _CHIP_PADDING_H, y, actual_chip_w - _CHIP_PADDING_H, chip_h),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    chip_text,
                )

                x += actual_chip_w + _CHIP_GAP

            painter.restore()
            return

        # Default painting for all other types.
        super().paint(painter, option, index)
