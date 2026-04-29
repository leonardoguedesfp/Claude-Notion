"""§3.9 FilterBar — strip above the table that shows active column filters
as removable chips with a "Limpar todos" link on the right."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    LIGHT,
    Palette,
    SP_2,
    SP_3,
)


_MAX_FILTER_CHIPS: int = 8


class _FilterChip(QFrame):
    """A single filter chip: '<Column>: N' + × button.

    Persistent widget — :meth:`update` mutates label/visibility instead of
    creating new chips on every filter change.
    """

    removed: Signal = Signal(str)  # emits the column key when × is clicked

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._key = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SP_3, 0, SP_2, 0)
        layout.setSpacing(SP_2)

        self._label = QLabel("")
        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self._on_close)

        layout.addWidget(self._label)
        layout.addWidget(self._close_btn)
        self.setVisible(False)
        self._restyle()

    def update_chip(self, key: str, label: str, count: int) -> None:
        """Repoint this chip at a new (column key, display label, count)."""
        self._key = key
        if count > 0:
            self._label.setText(f"{label}: {count}")
        else:
            self._label.setText(label)
        self.setVisible(True)

    def hide_chip(self) -> None:
        self.setVisible(False)

    # Round 3a: apply_theme removido — paleta única LIGHT.

    def _on_close(self) -> None:
        if self._key:
            self.removed.emit(self._key)

    def _restyle(self) -> None:
        p = self._p
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {p.app_accent_soft};
                border: 1px solid {p.app_accent_soft};
                border-radius: 12px;
            }}
            """
        )
        self._label.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_accent};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                background: transparent;
                border: none;
            }}
            """
        )
        self._close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {p.app_accent};
                border: none;
                font-size: {FS_SM2}px;
                font-weight: {FW_BOLD};
                padding: 0;
            }}
            QPushButton:hover {{
                color: {p.app_danger};
            }}
            """
        )


class FilterBar(QWidget):
    """§3.9 horizontal strip of active-filter chips + summary + clear link.

    The bar is hidden when no filters are active. Calling :meth:`set_filters`
    populates / hides the chip pool. ``filter_removed(key)`` fires when the
    user clicks a chip's × button; ``clear_all_clicked`` fires for the link.
    """

    filter_removed: Signal = Signal(str)
    clear_all_clicked: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        # Round 3a: kwarg dark removido — paleta única LIGHT.
        super().__init__(parent)
        self._p: Palette = LIGHT
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, SP_2, 20, SP_2)
        layout.setSpacing(SP_3)

        # Summary count, e.g. "2 filtros ativos".
        self._summary = QLabel("")
        layout.addWidget(self._summary)

        # Chip pool — pre-allocated, hidden by default.
        self._chips: list[_FilterChip] = []
        for _ in range(_MAX_FILTER_CHIPS):
            chip = _FilterChip(self._p, self)
            chip.removed.connect(self.filter_removed)
            layout.addWidget(chip)
            self._chips.append(chip)

        layout.addStretch()

        # "Limpar todos" link on the right.
        self._clear_btn = QPushButton("Limpar todos")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setFlat(True)
        self._clear_btn.clicked.connect(self.clear_all_clicked)
        layout.addWidget(self._clear_btn)

        self.setVisible(False)
        self._restyle()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_filters(
        self,
        active: dict[str, tuple[str, int]],
    ) -> None:
        """Populate the chip pool from *active*.

        Parameters
        ----------
        active:
            Mapping of column key → (display label, count). An empty dict
            hides the bar entirely.
        """
        if not active:
            self.setVisible(False)
            for chip in self._chips:
                chip.hide_chip()
            return

        self.setVisible(True)
        n = len(active)
        word = "filtro" if n == 1 else "filtros"
        self._summary.setText(f"{n} {word} ativo{'s' if n > 1 else ''}")

        items = list(active.items())[:_MAX_FILTER_CHIPS]
        for i, chip in enumerate(self._chips):
            if i < len(items):
                key, (label, count) = items[i]
                chip.update_chip(key, label, count)
            else:
                chip.hide_chip()

    # Round 3a: apply_theme removido — paleta única LIGHT.

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _restyle(self) -> None:
        p = self._p
        self.setStyleSheet(
            f"FilterBar {{ background-color: {p.app_panel}; "
            f"border-bottom: 1px solid {p.app_border}; }}"
        )
        self._summary.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_fg_subtle};
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM}px;
                font-weight: {FW_BOLD};
                letter-spacing: 0.04em;
                text-transform: uppercase;
                background: transparent;
                border: none;
            }}
            """
        )
        self._clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {p.app_accent};
                border: none;
                font-family: "{FONT_BODY}", "Segoe UI", Arial, sans-serif;
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                text-decoration: underline;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {p.app_accent_hover};
            }}
            """
        )
