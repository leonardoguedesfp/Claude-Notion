"""QAbstractTableModel backed by the SQLite cache."""
from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from notion_bulk_edit.encoders import format_br_date, format_brl
from notion_bulk_edit.schemas import PropSpec, colunas_visiveis, get_prop, is_nao_editavel
from notion_rpadv.cache import db as cache_db
from notion_rpadv.theme.tokens import LIGHT

# BUG-V3: title key used when resolving relation page_ids to display names.
# Fase 3: defensive fallbacks legados (_LEGACY_TITLE_KEYS_BY_BASE,
# _title_value_for_record) removidos — cache convergiu para slugs do schema
# dinâmico (verificado via cache.db.records antes da Fase 3).
_TITLE_KEY_BY_BASE: dict[str, str] = {
    "Clientes": "nome",
    "Processos": "numero_do_processo",  # parser slugifica "Número do processo"
    "Tarefas": "tarefa",                # parser slugifica "Tarefa"
    "Catalogo": "nome",                 # parser slugifica "Nome"
}

# BUG-V2-04: title fragments that mark a Notion "template" row that must
# never appear in the user-facing tables, even if the sync filter missed it.
_TEMPLATE_TITLE_FRAGMENTS: tuple[str, ...] = (
    "🟧",
    "modelo — usar",
    "modelo - usar",
    "modelo -- usar",
    "modelo – usar",  # en-dash
)


def _looks_like_template_row(record: dict, title_key: str) -> bool:
    """BUG-V2-04: detect rows whose title matches the "Modelo — usar como
    template" convention. Case-insensitive, tolerant to em/en-dash variants.

    Fase 3: assinatura revertida para (record, title_key) — defensive
    fallback legado removido após cache convergir.
    """
    title = record.get(title_key)
    if not isinstance(title, str) or not title:
        return False
    lowered = title.lower()
    return any(frag.lower() in lowered for frag in _TEMPLATE_TITLE_FRAGMENTS)


def _count_processos_for_cliente(conn: sqlite3.Connection, cliente_page_id: str) -> int:
    """BUG-V2-09: count rows in the local Processos cache whose 'cliente'
    relation references *cliente_page_id*. Returns 0 if the cache has no
    Processos data yet."""
    if not cliente_page_id:
        return 0
    try:
        processos = cache_db.get_all_records(conn, "Processos")
    except Exception:  # noqa: BLE001
        return 0
    count = 0
    for proc in processos:
        rel = proc.get("cliente")
        if isinstance(rel, list) and cliente_page_id in (str(x) for x in rel):
            count += 1
    return count


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


_EMPTY_PLACEHOLDER: str = "—"  # §3.3 em-dash for null/empty cells


def _display_value(spec: PropSpec, raw: Any) -> str:
    """Convert a raw Python value to a human-readable string for DisplayRole.

    §3.3: null/empty cells render as a soft em-dash (rendered in
    ``app_fg_subtle`` by the model's ForegroundRole), not as blank space —
    so users can tell "no value" apart from "0" or "False".
    """
    if raw is None:
        return _EMPTY_PLACEHOLDER
    # BUG-V4: empty list should render as the placeholder, not '[]'
    if isinstance(raw, list) and len(raw) == 0:
        return _EMPTY_PLACEHOLDER
    if isinstance(raw, str) and raw.strip() == "":
        return _EMPTY_PLACEHOLDER
    tipo = spec.tipo
    if tipo == "number":
        # BUG-OP-05 follow-up: schemas declare ``formato="BRL"`` (uppercase)
        # but this comparison was lowercase, so currency cells rendered the
        # raw float ("78500.0") instead of "R$ 78.500,00". Without the
        # formatted string in DisplayRole, even the dual-role search couldn't
        # match a query like "R$ 78" — and the column itself was unreadable
        # for users who expected BR currency. Compare case-insensitively.
        if spec.formato.upper() == "BRL":
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
        # BUG-V2-10: False renders as blank (not "✗"/"x" which reads as a positive mark in pt-BR)
        return "✓" if raw else ""
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
    # BUG-OP-06: emitted when reload(preserve_dirty=True) drops a dirty entry
    # because the row was deleted remotely. (page_id, key)
    dirty_dropped: Signal = Signal(str, str)
    # BUG-OP-06: emitted when reload(preserve_dirty=True) detects a server-side
    # change conflicting with an unsaved local edit. (page_id, key,
    # local_value, remote_value). Values are typed as `object` because
    # multi_select / relation cells carry lists.
    dirty_conflict_detected: Signal = Signal(str, str, object, object)

    def __init__(
        self,
        base: str,
        conn: sqlite3.Connection,
        parent: Any = None,
        audit_conn: sqlite3.Connection | None = None,
        user_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._base = base
        self._conn = conn
        # BUG-OP-09: pending_edits/edit_log live in the audit database. A
        # caller (page) that knows about the split passes a dedicated
        # audit_conn; in-memory tests that share one conn for both schemas
        # fall back to the same handle.
        self._audit_conn: sqlite3.Connection = audit_conn or conn
        # Fase 4: user_id habilita prefs persistidas em meta_user_columns.
        # None mantém comportamento default (defaults do schema).
        self._user_id: str | None = user_id
        self._cols: list[str] = colunas_visiveis(base, user_id=user_id)
        self._rows: list[dict[str, Any]] = []
        # BUG-24: keyed by (page_id, key) instead of (row_idx, key)
        self._dirty: dict[tuple[str, str], Any] = {}
        # BUG-OP-06: snapshot of the cache value at the time the user started
        # editing each cell, used by reload(preserve_dirty=True) to detect
        # whether a sync-induced remote change conflicts with the local edit.
        self._dirty_original: dict[tuple[str, str], Any] = {}
        # P2-002 (Lote 2): cache de DisplayRole por (row, col).
        # Qt chama data() varias vezes por paint (DisplayRole,
        # ForegroundRole — que recursa em DisplayRole, FontRole, etc.).
        # Para colunas relation/date/multi_select o lookup e caro
        # (resolve relation, format BR date). Sem cache, em uma tabela
        # com 1100+ linhas o trabalho dobra. Invalidado em reload,
        # setData e clear_dirty.
        self._display_cache: dict[tuple[int, int], str] = {}
        self.reload()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def reload(self, *, preserve_dirty: bool = False) -> None:
        """Reload rows from SQLite and reset the model.

        BUG-OP-06: when called from the post-sync code path the caller passes
        ``preserve_dirty=True`` so unsaved edits survive the refresh. For
        each surviving dirty cell we still emit the conflict signal if the
        cache value moved while the user was editing. Cells whose row was
        deleted remotely are dropped and surfaced via ``dirty_dropped``.
        """
        self.beginResetModel()
        saved_dirty = dict(self._dirty) if preserve_dirty else {}
        saved_originals = dict(self._dirty_original) if preserve_dirty else {}

        # P2-002 (Lote 2): invalidar cache de DisplayRole — rows e cols
        # podem ter mudado, qualquer (row, col) prévio é stale.
        self._display_cache.clear()

        # Fase 4: recalcula _cols a partir das prefs atuais. O picker salva
        # em meta_user_columns e chama reload() — sem este recalc, a tabela
        # continua mostrando as colunas antigas até o próximo restart.
        self._cols = colunas_visiveis(self._base, user_id=self._user_id)

        rows = cache_db.get_all_records(self._conn, self._base)
        # BUG-V2-04: filter out template/sentinel rows by title pattern so the
        # "🟧 Modelo — usar como template" row never reaches the table view.
        title_key = _TITLE_KEY_BY_BASE.get(self._base, "")
        if title_key:
            rows = [r for r in rows if not _looks_like_template_row(r, title_key)]
        self._rows = rows

        if not preserve_dirty:
            self._dirty.clear()
            self._dirty_original.clear()
            self.endResetModel()
            self.dirty_changed.emit(False)
            return

        # Preserve-dirty path. Index new rows by page_id for O(1) lookup so
        # the reapply loop is O(N_dirty), not O(N_dirty * N_rows).
        rows_by_id = {r.get("page_id"): r for r in rows}
        kept_dirty: dict[tuple[str, str], Any] = {}
        kept_originals: dict[tuple[str, str], Any] = {}
        dropped: list[tuple[str, str]] = []
        conflicts: list[tuple[str, str, Any, Any]] = []

        for (page_id, key), local_value in saved_dirty.items():
            new_row = rows_by_id.get(page_id)
            if new_row is None:
                dropped.append((page_id, key))
                continue
            kept_dirty[(page_id, key)] = local_value
            original = saved_originals.get((page_id, key))
            kept_originals[(page_id, key)] = original
            new_remote = new_row.get(key)
            # Conflict iff the cache value at first-edit time differs from
            # the value the sync just brought down.
            if not _values_equal(original, new_remote):
                conflicts.append((page_id, key, local_value, new_remote))

        self._dirty = kept_dirty
        self._dirty_original = kept_originals
        self.endResetModel()

        for page_id, key in dropped:
            self.dirty_dropped.emit(page_id, key)
        for page_id, key, local_value, remote_value in conflicts:
            self.dirty_conflict_detected.emit(page_id, key, local_value, remote_value)
        self.dirty_changed.emit(bool(self._dirty))

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
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._cols):
                key = self._cols[section]
                spec = get_prop(self._base, key)
                label = spec.label if spec is not None else key
                if role == Qt.ItemDataRole.DisplayRole:
                    return label
                # §3.1: tooltip carries the full label so a user-shrunk column
                # still discloses what it represents.
                if role == Qt.ItemDataRole.ToolTipRole:
                    return label
            return None
        if role == Qt.ItemDataRole.DisplayRole:
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

        # BUG-V2-09: when the Notion rollup for "Nº de Processos" arrives empty
        # (common for data sources that haven't materialised the rollup yet),
        # compute the count locally by counting Processos rows referencing this
        # client's page_id. Keeps the column populated without re-syncing.
        if (
            self._base == "Clientes"
            and key == "n_processos"
            and (raw is None or raw == "" or raw == [])
        ):
            raw = _count_processos_for_cliente(self._conn, page_id)

        if role == Qt.ItemDataRole.DisplayRole:
            # P2-002 (Lote 2): cache de DisplayRole por (row, col).
            # Qt chama data() varias vezes por paint, e ForegroundRole
            # recursa em DisplayRole — sem cache, _resolve_relation /
            # format_br_date / format_brl rodam 2x+ por celula. Cache
            # invalidado em reload, setData, clear_dirty, discard_dirty.
            cache_key = (row_idx, col_idx)
            cached = self._display_cache.get(cache_key)
            if cached is not None:
                return cached
            if spec is not None:
                # BUG-V3: for relation columns, resolve page_ids to readable names
                if spec.tipo == "relation" and spec.target_base and isinstance(raw, list):
                    result = _resolve_relation(self._conn, raw, spec.target_base)
                else:
                    result = _display_value(spec, raw)
            else:
                result = str(raw) if raw is not None else ""
            self._display_cache[cache_key] = result
            return result

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
            # §3.3: dim the em-dash placeholder so it reads as "no value".
            display = self.data(index, Qt.ItemDataRole.DisplayRole)
            if display == _EMPTY_PLACEHOLDER:
                return QBrush(QColor(LIGHT.app_fg_subtle))
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
            # BUG-OP-06: drop the original snapshot too — the cell is no
            # longer dirty.
            self._dirty_original.pop(dirty_key, None)
        else:
            # BUG-OP-06: snapshot the pre-edit cache value the first time
            # the user dirties this cell. Subsequent edits keep the same
            # snapshot so conflict detection compares against the *original*
            # value the user saw, not their last typed-but-not-saved value.
            if dirty_key not in self._dirty_original:
                self._dirty_original[dirty_key] = original
            self._dirty[dirty_key] = value

        # P2-002 (Lote 2): invalidar cache de DisplayRole para a célula
        # editada — o valor display vai mudar.
        self._display_cache.pop((row_idx, col_idx), None)

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
        """Return list of edit dicts compatible with CommitWorker.

        Pure read — used by the dirty-counter UI. The returned ``id`` is 0
        because no DB row has been allocated yet; callers that intend to
        send these to the API should go through ``flush_dirty_to_pending``
        which persists each entry and returns dicts with real ids.
        """
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

    def flush_dirty_to_pending(self) -> list[dict[str, Any]]:
        """BUG-OP-01/02: persist each dirty cell to the *pending_edits*
        table and return the edits list with real ids.

        After CommitWorker confirms the API call, it calls
        ``cache_db.mark_edit_applied(edit_id, user)`` which moves the row
        from ``pending_edits`` (status='pending') to ``edit_log``. Without
        a real id at this point, that move never happens — that is BUG-OP-01.

        Idempotency (BUG-OP-02): if this method is called twice for the
        same dirty cell (e.g. retry after a transient API failure), the
        helper ``cache_db.upsert_pending_edit`` reuses the existing row's
        id rather than inserting a duplicate.

        Read-only-typed cells (rollup, formula, created_time,
        last_edited_time) are filtered out at the dirty-cell stage by the
        delegate, so they never reach this code path. We additionally guard
        here so the persistence layer never sees a non-encodable type.
        """
        result: list[dict[str, Any]] = []
        for (page_id, key), new_value in self._dirty.items():
            record = next(
                (r for r in self._rows if r.get("page_id") == page_id), None
            )
            if record is None:
                continue
            spec = get_prop(self._base, key)
            if spec is not None and spec.tipo in (
                "rollup", "formula", "created_time", "last_edited_time",
            ):
                continue
            # Use the snapshot taken at first edit so the revert chain is
            # anchored to what the user actually replaced, not to the live
            # cell value (which == the dirty value while editing).
            old_value: Any = self._dirty_original.get(
                (page_id, key), record.get(key)
            )
            # BUG-OP-09: route through the audit connection.
            edit_id = cache_db.upsert_pending_edit(
                self._audit_conn, self._base, page_id, key,
                old_value, new_value,
            )
            result.append({
                "id": edit_id,
                "base": self._base,
                "page_id": page_id,
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
            })
        return result

    def clear_dirty(
        self,
        cells_to_clear: list[tuple[str, str]] | None = None,
    ) -> None:
        """Mark cells as clean.

        BUG-OP-03: when ``cells_to_clear`` is passed, only those cells lose
        their dirty state — used after a partial save so the cells whose
        API call failed remain visibly dirty for retry. With the default
        ``None`` we fall back to the legacy "clear everything" behaviour
        used by post-revert and other paths.
        """
        if not self._dirty:
            return

        if cells_to_clear is None:
            keys_to_clear = list(self._dirty.keys())
        else:
            # Filter to keys that actually exist in _dirty so callers can
            # pass over-broad lists without raising.
            keys_to_clear = [k for k in cells_to_clear if k in self._dirty]

        if not keys_to_clear:
            return

        # Apply each cleared dirty value into the backing rows so reload
        # is not required.
        for (page_id, key) in keys_to_clear:
            new_value = self._dirty.get((page_id, key))
            for row in self._rows:
                if row.get("page_id") == page_id:
                    row[key] = new_value
                    break
            self._dirty.pop((page_id, key), None)
            # BUG-OP-06: snapshots are tied to the live dirty set.
            self._dirty_original.pop((page_id, key), None)

        # P2-002 (Lote 2): cells fizeram commit do dirty para o backing
        # row — display value pode mudar. Invalidar cache global é mais
        # simples e seguro que rastrear (page_id, key) → (row, col).
        self._display_cache.clear()

        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self._rows) - 1, len(self._cols) - 1),
            [Qt.ItemDataRole.BackgroundRole],
        )
        self.dirty_changed.emit(bool(self._dirty))

    def discard_dirty(self) -> None:
        """Revert all dirty cells to their original cached values."""
        if not self._dirty:
            return
        self._dirty.clear()
        # BUG-OP-06: discard drops both the dirty values and their snapshots.
        self._dirty_original.clear()
        # P2-002 (Lote 2): valores dirty saíram, display volta ao backing.
        self._display_cache.clear()
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self._rows) - 1, len(self._cols) - 1),
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.EditRole],
        )
        self.dirty_changed.emit(False)

    # ------------------------------------------------------------------
    # Row accessors
    # ------------------------------------------------------------------

    def cols(self) -> list[str]:
        """Fase 4: getter público da lista atual de colunas visíveis.

        Retorna uma cópia para que callers não mutilem o cache interno.
        Recalculado em ``reload()`` a partir do registry — pages e widgets
        externos devem chamar este getter em vez de tocar ``_cols``
        diretamente ou recalcular via ``colunas_visiveis(base)``."""
        return list(self._cols)

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
