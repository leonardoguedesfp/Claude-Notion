"""QAbstractTableModel backed by the SQLite cache."""
from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from notion_bulk_edit.encoders import format_br_date, format_brl
from notion_bulk_edit.schemas import PropSpec, colunas_visiveis, get_prop, is_nao_editavel
from notion_rpadv.cache import db as cache_db

# BUG-V3: title key used when resolving relation page_ids to display names
_TITLE_KEY_BY_BASE: dict[str, str] = {
    "Clientes": "nome",
    "Processos": "cnj",
    "Tarefas": "titulo",
    "Catalogo": "titulo",
}


def _resolve_relation(conn: sqlite3.Connection, page_ids: list, target_base: str) -> str:
    """BUG-V3: resolve a list of page_ids to display names via the local cache."""
    if not page_ids or not target_base:
        return ""
    title_key = _TITLE_KEY_BY_BASE.get(target_base, "nome")
    names: list[str] = []
    for pid in page_ids[:3]:
        rec = cache_db.get_record(conn, target_base, str(pid))
        if rec is None:
            names.append("—")
        else:
            names.append(str(rec.get(title_key) or "—"))
    extra = f" +{len(page_ids) - 3}" if len(page_ids) > 3 else ""
    return ", ".join(names) + extra

# Background colours (ARGB strings, styled via the app palette or hard-coded).
_COLOR_DIRTY = QColor("#FFF9C4")       # pale yellow for dirty cells
_COLOR_ROW_ALT = QColor("#F5F5F5")    # alternating row tint
_COLOR_ROW_EVEN = QColor("#FFFFFF")


def _display_value(spec: PropSpec, raw: Any) -> str:
    """Convert a raw Python value to a human-readable string for DisplayRole."""
    if raw is None:
        return ""
    # BUG-V4: empty list should render as blank, not '[]'
    if isinstance(raw, list) and len(raw) == 0:
        return ""
    tipo = spec.tipo
    if tipo == "number":
        if spec.formato == "brl":
            try:
                return format_brl(float(raw))
            except (TypeError, ValueError):
                return str(raw)
        try:
            return str(raw)
        except Exception:  # noqa: BLE001
            return ""
    if tipo in ("date", "created_time", "last_edited_time"):
        try:
            return format_br_date(str(raw))
        except Exception:  # noqa: BLE001
            return str(raw)
    if tipo == "checkbox":
        return "✓" if raw else "✗"
    if tipo == "multi_select":
        if isinstance(raw, list):
            return ", ".join(str(v) for v in raw)
        return str(raw)
    # BUG-V3: relation — raw is list[page_id]; display is resolved in data() below
    if tipo == "relation":
        if isinstance(raw, list):
            return ", ".join(str(v) for v in raw)
        return str(raw)
    # BUG-EXEC-08: rollup arrays render as comma-joined values, not Python repr
    if tipo == "rollup":
        if isinstance(raw, list):
            return ", ".join(str(v) for v in raw if v is not None)
        return str(raw)
    if isinstance(raw, list):
        return ", ".join(str(v) for v in raw if v is not None)
    return str(raw)


def _values_equal(a: Any, b: Any) -> bool:
    """BUG-25: safe equality that handles list/bool/None/date mismatches."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, list) and isinstance(b, list):
        return sorted(str(x) for x in a) == sorted(str(x) for x in b)
    if type(a) is not type(b):
        return str(a) == str(b)
    return a == b


class BaseTableModel(QAbstractTableModel):
    """QAbstractTableModel backed by SQLite cache for a single Notion base."""

    dirty_changed: Signal = Signal(bool)

    def __init__(
        self,
        base: str,
        conn: sqlite3.Connection,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._base = base
        self._conn = conn
        self._cols: list[str] = colunas_visiveis(base)
        self._rows: list[dict[str, Any]] = []
        # BUG-24: keyed by (page_id, key) instead of (row_idx, key)
        self._dirty: dict[tuple[str, str], Any] = {}
        self.reload()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload rows from SQLite and reset the model."""
        self.beginResetModel()
        self._rows = cache_db.get_all_records(self._conn, self._base)
        self._dirty.clear()
        self.endResetModel()
        self.dirty_changed.emit(False)

    # ------------------------------------------------------------------
    # QAbstractTableModel overrides
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._cols)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._cols):
                key = self._cols[section]
                spec = get_prop(self._base, key)
                if spec is not None:
                    return spec.label
                return key
        else:
            return str(section + 1)
        return None

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None
        row_idx = index.row()
        col_idx = index.column()
        if row_idx < 0 or row_idx >= len(self._rows):
            return None
        if col_idx < 0 or col_idx >= len(self._cols):
            return None

        key = self._cols[col_idx]
        spec = get_prop(self._base, key)
        record = self._rows[row_idx]

        # BUG-24: dirty key uses (page_id, key)
        page_id = record.get("page_id", "")
        dirty_key = (page_id, key)
        is_dirty = dirty_key in self._dirty

        # Raw value: prefer dirty override, fall back to cached.
        raw: Any = self._dirty[dirty_key] if is_dirty else record.get(key)

        if role == Qt.ItemDataRole.DisplayRole:
            if spec is not None:
                # BUG-V3: for relation columns, resolve page_ids to readable names
                if spec.tipo == "relation" and spec.target_base and isinstance(raw, list):
                    return _resolve_relation(self._conn, raw, spec.target_base)
                return _display_value(spec, raw)
            return str(raw) if raw is not None else ""

        if role == Qt.ItemDataRole.EditRole:
            return raw

        # UserRole+1 → dirty flag
        if role == Qt.ItemDataRole.UserRole + 1:
            return is_dirty

        if role == Qt.ItemDataRole.BackgroundRole:
            if is_dirty:
                return QBrush(_COLOR_DIRTY)
            if row_idx % 2 == 1:
                return QBrush(_COLOR_ROW_ALT)
            return QBrush(_COLOR_ROW_EVEN)

        if role == Qt.ItemDataRole.ForegroundRole:
            return None

        if role == Qt.ItemDataRole.FontRole:
            if spec is not None and spec.mono:
                font = QFont("Courier New", 9)
                font.setStyleHint(QFont.StyleHint.Monospace)
                return font
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if spec is not None and spec.tipo == "number":
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def setData(
        self,
        index: QModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if role != Qt.ItemDataRole.EditRole:
            return False
        if not index.isValid():
            return False

        row_idx = index.row()
        col_idx = index.column()
        if row_idx < 0 or row_idx >= len(self._rows):
            return False
        if col_idx < 0 or col_idx >= len(self._cols):
            return False

        key = self._cols[col_idx]
        record = self._rows[row_idx]
        # BUG-24: key by page_id, not row_idx
        page_id = record.get("page_id", "")
        dirty_key = (page_id, key)
        original = record.get(key)

        # BUG-25: use type-aware comparison instead of bare ==
        if _values_equal(value, original):
            self._dirty.pop(dirty_key, None)
        else:
            self._dirty[dirty_key] = value

        self.dataChanged.emit(index, index, [role, Qt.ItemDataRole.BackgroundRole])
        # BUG-29: removed unused had_dirty variable
        self.dirty_changed.emit(bool(self._dirty))
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid():
            return base_flags

        col_idx = index.column()
        if col_idx < 0 or col_idx >= len(self._cols):
            return base_flags

        key = self._cols[col_idx]
        # BUG-02 + BUG-03: correct arity and removed broken obrigatorio check
        if not is_nao_editavel(self._base, key):
            return base_flags | Qt.ItemFlag.ItemIsEditable
        return base_flags

    # ------------------------------------------------------------------
    # Dirty-edit helpers
    # ------------------------------------------------------------------

    def get_dirty_edits(self) -> list[dict[str, Any]]:
        """Return list of edit dicts compatible with CommitWorker."""
        result: list[dict[str, Any]] = []
        for (page_id, key), new_value in self._dirty.items():
            record = next((r for r in self._rows if r.get("page_id") == page_id), None)
            if record is None:
                continue
            old_value: Any = record.get(key)
            result.append({
                "id": 0,
                "base": self._base,
                "page_id": page_id,
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
            })
        return result

    def clear_dirty(self) -> None:
        """Mark all cells as clean (called after saving)."""
        if not self._dirty:
            return
        # Apply dirty values into the backing rows so reload is not required.
        for (page_id, key), new_value in self._dirty.items():
            for row in self._rows:
                if row.get("page_id") == page_id:
                    row[key] = new_value
                    break
        self._dirty.clear()
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self._rows) - 1, len(self._cols) - 1),
            [Qt.ItemDataRole.BackgroundRole],
        )
        self.dirty_changed.emit(False)

    def discard_dirty(self) -> None:
        """Revert all dirty cells to their original cached values."""
        if not self._dirty:
            return
        self._dirty.clear()
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self._rows) - 1, len(self._cols) - 1),
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.EditRole],
        )
        self.dirty_changed.emit(False)

    # ------------------------------------------------------------------
    # Row accessors
    # ------------------------------------------------------------------

    def get_page_id(self, row: int) -> str:
        """Return the Notion page_id for a given row index."""
        if 0 <= row < len(self._rows):
            return str(self._rows[row].get("page_id", ""))
        return ""

    def get_record(self, row: int) -> dict[str, Any]:
        """Return the full decoded record dict for a given row index."""
        if 0 <= row < len(self._rows):
            return dict(self._rows[row])
        return {}
