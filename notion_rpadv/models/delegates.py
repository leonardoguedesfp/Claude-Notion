"""Item delegates for inline editing in the table."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QDate, QModelIndex, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
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
from notion_rpadv.widgets.multi_select_editor import MultiSelectEditor

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
            # P1-003 (Lote 1): popup customizado com checkboxes do
            # spec.opcoes. Antes era QLineEdit livre, que aceitava typo do
            # usuário e silenciosamente criava opção fantasma no schema
            # do Notion.
            return MultiSelectEditor(spec, parent)

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

        if tipo == "multi_select" and isinstance(editor, MultiSelectEditor):
            # raw é list (cache) ou string CSV (fallback). MultiSelectEditor
            # aceita lista e descarta itens fora de spec.opcoes.
            if isinstance(raw, list):
                editor.set_values([str(v) for v in raw])
            elif isinstance(raw, str) and raw:
                editor.set_values(
                    [v.strip() for v in raw.split(",") if v.strip()],
                )
            else:
                editor.set_values([])
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

        if tipo == "multi_select" and isinstance(editor, MultiSelectEditor):
            # P1-003 (Lote 1): editor.values() já garante que retorna só
            # opções válidas em spec.opcoes (sem typo / sem ghost).
            value = editor.values()
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

        # §3.2: relation cells render as accent chip-rels — visually distinct
        # from select/multi_select chips and clickable (the click handling is
        # wired up in BaseTablePage via the table's doubleClicked signal).
        if spec is not None and spec.tipo == "relation":
            raw: Any = index.data(Qt.ItemDataRole.DisplayRole)
            text = str(raw) if raw else ""
            super().paint(painter, option, index)
            if not text or text == "—":
                return
            # Split the comma-resolved name list back into chips.
            names = [n.strip() for n in text.split(",") if n.strip()]
            if not names:
                return

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = option.rect
            x = rect.x() + _CHIP_PADDING_H
            y = rect.y() + (rect.height() - 20) // 2

            font = QApplication.font()
            font.setPointSize(8)
            painter.setFont(font)
            fm = painter.fontMetrics()

            # Accent-tinted chip — DELTA "chip cor --accent (chip-rel)".
            from notion_rpadv.theme.tokens import LIGHT
            chip_bg = QColor(LIGHT.app_accent_soft)
            chip_fg = QColor(LIGHT.app_accent)

            for name in names:
                if x >= rect.right() - _CHIP_PADDING_H:
                    break
                text_w = fm.horizontalAdvance(name)
                chip_w = text_w + _CHIP_PADDING_H * 2
                chip_h = fm.height() + _CHIP_PADDING_V * 2

                chip_rect_right = min(x + chip_w, rect.right() - _CHIP_PADDING_H)
                actual_w = chip_rect_right - x

                painter.setBrush(QBrush(chip_bg))
                painter.setPen(Qt.PenStyle.NoPen)
                from PySide6.QtCore import QRectF
                painter.drawRoundedRect(
                    QRectF(x, y, actual_w, chip_h), _CHIP_RADIUS, _CHIP_RADIUS
                )
                painter.setPen(QPen(chip_fg))
                from PySide6.QtCore import QRect as _QRect
                painter.drawText(
                    _QRect(x + _CHIP_PADDING_H, y, actual_w - _CHIP_PADDING_H, chip_h),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    name,
                )
                x += actual_w + _CHIP_GAP
            painter.restore()
            return

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


class SucessorDelegate(QStyledItemDelegate):
    """§3.7 paints the "Sucessor de" column as `↳ Nome (†)` when set,
    or as the empty placeholder when not.

    It also draws the value with the chip-rel accent treatment so the cell
    visually anchors the user back to the parent record.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        super().paint(painter, option, QModelIndex())
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not text or text == "—":
            super().paint(painter, option, index)
            return

        from notion_rpadv.theme.tokens import LIGHT
        accent_fg = QColor(LIGHT.app_accent)
        rect = option.rect

        painter.save()
        # P0-001 (Lote 1): clip explícito ao retângulo da célula. Mesmo
        # anti-pattern do CnjDelegate (super().paint com QModelIndex
        # inválido + ausência de setClipRect) — proteger contra ghosts
        # de pintura.
        painter.setClipRect(option.rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(QApplication.font())
        f.setItalic(True)
        f.setPointSize(9)
        painter.setFont(f)
        painter.setPen(QPen(accent_fg))
        # Draw "↳ <name> (†)" — the cross marker emphasises the
        # successor-of-a-deceased nuance from DELTA §3.7.
        painter.drawText(
            QRect(rect.x() + 8, rect.y(), rect.width() - 12, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"↳ {text} (†)",
        )
        painter.restore()


class CnjDelegate(QStyledItemDelegate):
    """§3.8 paints the CNJ column with a two-line layout when the row has
    a ``processo_pai`` relation set.

    Layout:
      ↳ <CNJ pai>      — small monospace, muted
      <CNJ próprio>    — normal monospace, strong colour

    Falls back to default rendering for processes with no parent.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        # Locate the source model (resolve through the proxy chain) so we
        # can pull the sibling 'processo_pai' value and the cache lookup.
        model = index.model()
        src_index = index
        while hasattr(model, "sourceModel"):
            src_model = model.sourceModel()
            src_index = model.mapToSource(src_index) if hasattr(model, "mapToSource") else src_index
            model = src_model

        cols: list[str] | None = getattr(model, "_cols", None)
        base: str | None = getattr(model, "_base", None)
        conn = getattr(model, "_conn", None)

        # Default painting if we can't resolve sibling data.
        if cols is None or base != "Processos" or conn is None:
            super().paint(painter, option, index)
            return

        # Look up the row's processo_pai cell value (list[page_id]).
        try:
            row = src_index.row()
            record = model.get_record(row) if hasattr(model, "get_record") else {}
            parent_ids = record.get("processo_pai") or []
        except Exception:  # noqa: BLE001
            parent_ids = []

        # Resolve parent CNJ from cache (may be empty if parent not synced).
        # Fase 3: fallback legado 'cnj' removido — schema dinâmico já é a
        # fonte única e cache convergiu para 'numero_do_processo'.
        parent_cnj = ""
        if isinstance(parent_ids, list) and parent_ids:
            try:
                from notion_rpadv.cache import db as cache_db
                parent_rec = cache_db.get_record(conn, "Processos", str(parent_ids[0]))
                if parent_rec is not None:
                    parent_cnj = str(parent_rec.get("numero_do_processo") or "")
            except Exception:  # noqa: BLE001
                parent_cnj = ""

        if not parent_cnj:
            # No (resolvable) parent — let the default delegate paint.
            super().paint(painter, option, index)
            return

        # ----- Two-line render -----
        # Background first (selection / dirty / alternating).
        super().paint(painter, option, QModelIndex())

        own_cnj = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        rect = option.rect
        painter.save()
        # P0-001 (Lote 1): clip explícito ao retângulo da célula. Sem isso,
        # o ``super().paint(painter, option, QModelIndex())`` (índice
        # inválido na linha que pinta apenas o background) deixa o painter
        # em estado de clip indeterminado, e os ``drawText`` abaixo podem
        # vazar texto sobre células adjacentes em paths de repaint parcial
        # (scroll). Reportado pelo usuário como ghosts de CNJ flutuando.
        painter.setClipRect(option.rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Pull palette tokens for the muted/strong text colours.
        from notion_rpadv.theme.tokens import LIGHT
        muted = QColor(LIGHT.app_fg_subtle)
        strong = QColor(LIGHT.app_fg_strong)

        # Top line: parent CNJ in smaller monospace.
        top_font = QFont("Courier New")
        top_font.setPixelSize(10)
        painter.setFont(top_font)
        painter.setPen(QPen(muted))
        top_rect = QRect(
            rect.x() + 8, rect.y() + 4, rect.width() - 12, rect.height() // 2 - 2
        )
        painter.drawText(
            top_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"↳ {parent_cnj}",
        )

        # Bottom line: own CNJ.
        bot_font = QFont("Courier New")
        bot_font.setPixelSize(12)
        bot_font.setBold(True)
        painter.setFont(bot_font)
        painter.setPen(QPen(strong))
        bot_rect = QRect(
            rect.x() + 8,
            rect.y() + rect.height() // 2,
            rect.width() - 12,
            rect.height() // 2 - 2,
        )
        painter.drawText(
            bot_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            own_cnj,
        )

        painter.restore()

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> Any:
        size = super().sizeHint(option, index)
        # §3.8: rows with a parent are taller; force a uniform tall row so
        # mixed grids stay aligned.
        size.setHeight(max(size.height(), 38))
        return size
