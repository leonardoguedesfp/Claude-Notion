"""QSortFilterProxyModel for searching and filtering the table."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt


class TableFilterProxy(QSortFilterProxyModel):
    """Supports free-text search across all columns and per-column value filters.

    Usage::

        proxy = TableFilterProxy()
        proxy.setSourceModel(my_table_model)

        # Live search (matches any column).
        proxy.set_search("Silva")

        # Allow only rows where column 3 is "Ativo" or "Pendente".
        proxy.set_col_filter(3, {"Ativo", "Pendente"})

        # Clear everything.
        proxy.clear_filters()
    """

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._search_text: str = ""
        self._col_filters: dict[int, set[str]] = {}
        # Case-insensitive by default.
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_search(self, text: str) -> None:
        """Set the free-text search string and refresh the view."""
        normalised = text.strip()
        if normalised == self._search_text:
            return
        self._search_text = normalised
        self.invalidateRowsFilter()

    def set_col_filter(self, col: int, values: set[str] | None) -> None:
        """Restrict *col* to the given *values*.  Pass ``None`` to remove the filter."""
        if values is None or len(values) == 0:
            self._col_filters.pop(col, None)
        else:
            self._col_filters[col] = values
        self.invalidateRowsFilter()

    def clear_filters(self) -> None:
        """Remove the text search and all column filters."""
        changed = bool(self._search_text) or bool(self._col_filters)
        self._search_text = ""
        self._col_filters.clear()
        if changed:
            self.invalidateRowsFilter()

    def get_active_col_filter(self, col: int) -> set[str] | None:
        """Return the current allowed-value set for *col*, or None."""
        return self._col_filters.get(col)

    def has_any_filter(self) -> bool:
        """Return True if any search text or column filter is active."""
        return bool(self._search_text) or bool(self._col_filters)

    # ------------------------------------------------------------------
    # QSortFilterProxyModel override
    # ------------------------------------------------------------------

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex
    ) -> bool:
        """Return True if the row should be visible given current filters."""
        source = self.sourceModel()
        if source is None:
            return True

        col_count = source.columnCount(source_parent)

        # --- Per-column value filters ---
        for col, allowed in self._col_filters.items():
            if col >= col_count:
                continue
            idx = source.index(source_row, col, source_parent)
            # BUG-28: compare against UserRole (canonical value), not DisplayRole text
            # DisplayRole may be formatted ('✓', 'R$ 78.500') which breaks matching
            raw_val = source.data(idx, Qt.ItemDataRole.UserRole)
            if raw_val is None:
                raw_val = source.data(idx, Qt.ItemDataRole.EditRole)
            if raw_val is None:
                cell_display = ""
            elif isinstance(raw_val, list):
                cell_display = ", ".join(str(v) for v in raw_val)
            else:
                cell_display = str(raw_val)
            # For multi-value cells (comma-separated chips) check intersection.
            cell_values = {v.strip() for v in cell_display.split(",") if v.strip()}
            if not cell_values:
                cell_values = {cell_display}
            if not (cell_values & allowed):
                return False

        # --- Free-text search ---
        if self._search_text:
            needle = self._search_text.lower()
            matched = False
            for col in range(col_count):
                idx = source.index(source_row, col, source_parent)
                cell_display = str(
                    source.data(idx, Qt.ItemDataRole.DisplayRole) or ""
                )
                if needle in cell_display.lower():
                    matched = True
                    break
            if not matched:
                return False

        return True

    # ------------------------------------------------------------------
    # Convenience: unique values for a column (for filter dropdowns)
    # ------------------------------------------------------------------

    def unique_source_values(self, source_col: int) -> list[str]:
        """Return sorted unique canonical values from the *source* model column.

        BUG-28: uses EditRole (canonical values) so filter state matches filterAcceptsRow.
        """
        source = self.sourceModel()
        if source is None:
            return []
        seen: set[str] = set()
        result: list[str] = []
        row_count = source.rowCount()
        for row in range(row_count):
            idx = source.index(row, source_col)
            raw = source.data(idx, Qt.ItemDataRole.EditRole)
            if isinstance(raw, list):
                cell = ", ".join(str(v) for v in raw)
            elif raw is None:
                cell = ""
            else:
                cell = str(raw)
            # Split multi-select values.
            parts = [v.strip() for v in cell.split(",") if v.strip()]
            if not parts:
                parts = [cell]
            for part in parts:
                if part and part not in seen:
                    seen.add(part)
                    result.append(part)
        result.sort(key=str.lower)
        return result
