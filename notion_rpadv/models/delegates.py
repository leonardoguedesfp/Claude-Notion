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
from notion_rpadv.theme.tokens import LIGHT, parse_color, resolve_chip_color
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

# Round 3b-2: paleta de chips agora vem de
# notion_rpadv.theme.tokens.resolve_chip_color (override map em
# colors_overrides.py + paleta brand). Antes usava
# notion_colors.chip_colors_for que mimetizava cores do Notion web —
# substituído porque a paleta brand do escritório vence sobre Notion.
_CHIP_PADDING_H = 6
_CHIP_PADDING_V = 2
_CHIP_RADIUS = 10
_CHIP_GAP = 4


def _get_spec_meta_from_index(
    index: QModelIndex,
) -> tuple[PropSpec | None, str, str]:
    """Retrieve PropSpec + (base_label, prop_key) for the column of *index*.

    Round 3b-2: callers que pintam chips precisam de base+key pra consultar
    o override map. Antes só ``_get_spec_from_index`` existia (devolvia só
    o spec).
    """
    model = index.model()
    # Support proxy models.
    while hasattr(model, "sourceModel"):
        model = model.sourceModel()  # type: ignore[union-attr]
    base: str = getattr(model, "_base", "") or ""
    cols: list[str] | None = getattr(model, "_cols", None)
    if not base or cols is None:
        return None, "", ""
    col_idx = index.column()
    if col_idx < 0 or col_idx >= len(cols):
        return None, base, ""
    key = cols[col_idx]
    return get_prop(base, key), base, key


def _get_spec_from_index(index: QModelIndex) -> PropSpec | None:
    """Retrieve the PropSpec for the column represented by *index*."""
    spec, _base, _key = _get_spec_meta_from_index(index)
    return spec


class PropDelegate(QStyledItemDelegate):
    """Universal delegate — creates the right editor widget based on PropSpec.tipo."""

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Hotfix paint ghosts v2: zera ``option.text`` para tipos que
        renderizam chips customizados. Sem isso, ``super().paint()`` no
        caminho desses tipos pinta o display text como background, e o
        chip arredondado por cima não cobre 100% — sobra letra final
        vazando à direita.

        O override é virtual e Qt o invoca de dentro de
        ``QStyledItemDelegate.paint`` antes de pintar — daí termos que
        zerar AQUI, não no chamador (o helper v1 zerava na cópia mas Qt
        chamava ``initStyleOption`` de novo internamente, repopulando
        opt.text).

        Para tipos sem chip (rich_text, number, date, checkbox como
        texto), preserva o comportamento padrão de Qt — texto é pintado
        normalmente.
        """
        super().initStyleOption(option, index)
        spec = _get_spec_from_index(index)
        if spec is not None and spec.tipo in (
            "relation", "select", "multi_select",
        ):
            option.text = ""
            option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasDisplay

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
            # Round 3b-2: passa base+key pro editor consultar override map.
            _spec, base_label, prop_key = _get_spec_meta_from_index(index)
            return MultiSelectEditor(
                spec, parent, base_label=base_label, prop_key=prop_key,
            )

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
            # Hotfix paint ghosts v2: super().paint pinta background sem
            # texto porque o initStyleOption override desta classe zera
            # opt.text para tipos de chip. Sem o override, Qt chamava
            # initStyleOption internamente e repopulava o text — o helper
            # _paint_background_only do v1 era furado por isso.
            super().paint(painter, option, index)
            if not text or text == "—":
                # Sem chips para desenhar — pintar "—" manualmente
                # porque initStyleOption zerou o text default.
                if text == "—":
                    painter.save()
                    painter.setClipRect(option.rect)
                    painter.setPen(QPen(QColor(LIGHT.app_fg_subtle)))
                    painter.drawText(
                        option.rect.adjusted(8, 0, -4, 0),
                        Qt.AlignmentFlag.AlignVCenter
                        | Qt.AlignmentFlag.AlignLeft,
                        text,
                    )
                    painter.restore()
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
            # Round 3b-2 hotfix: app_accent_soft é rgba string ("rgba(16,64,99,0.08)").
            # QColor("rgba(...)") cai em inválido e renderiza PRETO. Antes do fix,
            # chips de relação (coluna Clientes, Processo pai etc.) apareciam com
            # fundo preto sobre cream e texto navy quase ilegível. parse_color
            # devolve componentes int explícitos pra QColor(r, g, b, a).
            bg_r, bg_g, bg_b, bg_a = parse_color(LIGHT.app_accent_soft)
            fg_r, fg_g, fg_b, _ = parse_color(LIGHT.app_accent)
            chip_bg = QColor(bg_r, bg_g, bg_b, bg_a)
            chip_fg = QColor(fg_r, fg_g, fg_b)

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

            # Hotfix paint ghosts v2: super().paint pinta background sem
            # texto porque o initStyleOption override desta classe zera
            # opt.text para tipos de chip. O helper v1 era furado porque
            # Qt repopulava opt.text via initStyleOption interno.
            super().paint(painter, option, index)

            if not values:
                # Sem valores — pintar "—" manualmente porque
                # initStyleOption zerou o text default.
                raw_display = index.data(Qt.ItemDataRole.DisplayRole)
                placeholder = (
                    "—" if raw_display in (None, "", "—") else str(raw_display)
                )
                painter.save()
                painter.setClipRect(option.rect)
                painter.setPen(QPen(QColor("#9CA3AF")))
                painter.drawText(
                    option.rect.adjusted(8, 0, -4, 0),
                    Qt.AlignmentFlag.AlignVCenter
                    | Qt.AlignmentFlag.AlignLeft,
                    placeholder,
                )
                painter.restore()
                return

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            rect = option.rect
            x = rect.x() + _CHIP_PADDING_H
            y = rect.y() + (rect.height() - 20) // 2  # vertically centred

            # Round 3b-2: cor agora vem do override map (paleta brand do
            # escritório), não mais do hex que o Notion configurou. Precisa
            # de base+key pra consultar.
            _spec_again, base_label, prop_key = _get_spec_meta_from_index(index)

            font = QApplication.font()
            font.setPointSize(8)
            painter.setFont(font)
            fm = painter.fontMetrics()

            for chip_text in values:
                if x >= rect.right() - _CHIP_PADDING_H:
                    break  # no more space

                # Round 3b-2: lookup direto no override map. Brand vence Notion.
                # Sem entry → ChipPalette default (cinza neutro), sem crash.
                pal = resolve_chip_color(base_label, prop_key, chip_text)
                bg_r, bg_g, bg_b, bg_a = parse_color(pal.bg)
                fg_r, fg_g, fg_b, _fg_a = parse_color(pal.fg)
                bg = QColor(bg_r, bg_g, bg_b, bg_a)
                fg = QColor(fg_r, fg_g, fg_b)

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

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Hotfix paint ghosts v2: zera ``option.text`` quando há valor a
        renderizar customizado. Quando não há valor (vazio ou ``—``),
        preserva o text para Qt pintar o placeholder normalmente."""
        super().initStyleOption(option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if text and text != "—":
            option.text = ""
            option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasDisplay

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        # Hotfix paint ghosts v2: super().paint pinta o background sempre
        # com índice válido. Quando há valor a renderizar customizado, o
        # initStyleOption override desta classe zera opt.text — Qt pinta
        # apenas background. Quando não há valor (vazio ou "—"),
        # initStyleOption preserva o text e Qt pinta o placeholder
        # normalmente. Antes, o ``super().paint(... QModelIndex())`` com
        # índice inválido era hack para suprimir o text — não é mais
        # necessário.
        super().paint(painter, option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if not text or text == "—":
            return

        accent_fg = QColor(LIGHT.app_accent)
        rect = option.rect

        painter.save()
        # P0-001 (Lote 1): clip explícito ao retângulo da célula —
        # defesa em profundidade contra paint hints distantes.
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


# Round simplificação CnjDelegate (Lote 1): classe removida.
#
# Antes, CnjDelegate desenhava a coluna numero_do_processo com layout
# two-line quando a linha tinha processo_pai resolvido — ↳ parent_cnj
# pequeno em cima do own_cnj em bold. Decisão de design:
#
# 1. Hierarquia processual já é visível pela coluna "Processo pai"
#    (relation, oculta por default no picker da Fase 4 — usuário
#    habilita se quiser). Two-line era redundância.
# 2. O custo da renderização customizada acumulou:
#    - bug de scroll ghost (Round 1) que o setClipRect mascarou.
#    - bug de Qt repopular opt.text via initStyleOption interno
#      (hotfix v2) que demandou override de virtual + paint manual
#      do CNJ no fallback.
# 3. Sem CnjDelegate, a coluna numero_do_processo cai no caminho
#    default de PropDelegate.paint (último super().paint do método),
#    que pinta texto em font default. Visualmente uniforme em todas
#    as linhas, sem ghost possível.
#
# A coluna "Processo pai" ganha uso real: chip de relation azul claro,
# clicável (double-click navega para o pai). Substituto melhor.
