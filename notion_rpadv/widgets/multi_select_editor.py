"""P1-003 (Lote 1): editor inline para campos multi_select.

Antes da Fase desta correção, o multi_select editava como ``QLineEdit``
com placeholder "Comma-separated values…". Usuário podia digitar texto
livre — typo virava nova opção fantasma no schema do Notion (silenciosa
poluição). Validador local em ``validators.py`` só rodava no fluxo de
import.

Este editor:
- Mostra chips dos valores atualmente selecionados (com cor do schema).
- Botão "▾" abre QMenu com QCheckBox por opção válida em ``spec.opcoes``.
- ``values()`` retorna apenas opções marcadas (sempre dentro do spec
  por construção).
- ``set_values()`` filtra valores fora do ``spec.opcoes`` (descarta o
  ruído).
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from notion_bulk_edit.schemas import PropSpec
from notion_rpadv.theme.tokens import resolve_chip_color


# Estilo de chip pequeno (compatível com PropDelegate paint).
_CHIP_PADDING_H = 6
_CHIP_PADDING_V = 2
_CHIP_RADIUS = 10


class MultiSelectEditor(QWidget):
    """Editor inline para multi_select. Construído com checkboxes do
    ``spec.opcoes`` — impede typos do usuário criarem opção fantasma no
    Notion."""

    def __init__(
        self,
        spec: PropSpec,
        parent: QWidget | None = None,
        *,
        base_label: str = "",
        prop_key: str = "",
    ) -> None:
        super().__init__(parent)
        self._spec = spec
        # Round 3b-2: base+prop_key pra consultar override map.
        self._base_label = base_label
        self._prop_key = prop_key
        # Validação na fonte: nunca aceitar valor fora do spec.
        self._allowed: set[str] = set(spec.opcoes or ())
        self._selected: set[str] = set()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Container de chips à esquerda (preenchido em _refresh_chips).
        self._chips_container = QWidget(self)
        self._chips_layout = QHBoxLayout(self._chips_container)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(2)
        self._chips_layout.addStretch()
        layout.addWidget(self._chips_container, stretch=1)

        # Botão "▾" abre o popup.
        self._open_btn = QToolButton(self)
        self._open_btn.setText("▾")
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.setStyleSheet(
            "QToolButton { border: none; padding: 2px 6px; "
            "color: #555; background: transparent; }"
            "QToolButton:hover { background: #E5E7EB; border-radius: 4px; }"
        )
        self._open_btn.clicked.connect(self._open_picker)
        layout.addWidget(self._open_btn)

        self._refresh_chips()

    # ------------------------------------------------------------------
    # API pública (consumida pelo PropDelegate)
    # ------------------------------------------------------------------

    def set_values(self, values: list[str] | None) -> None:
        """Carrega os valores marcados. Itens fora de ``spec.opcoes`` são
        descartados — proteção contra valores legados ou injetados."""
        if not values:
            self._selected = set()
        else:
            self._selected = {v for v in values if v in self._allowed}
        self._refresh_chips()

    def values(self) -> list[str]:
        """Retorna selecionados na ordem original do ``spec.opcoes``."""
        return [opt for opt in self._spec.opcoes if opt in self._selected]

    # ------------------------------------------------------------------
    # UI internals
    # ------------------------------------------------------------------

    def _open_picker(self) -> None:
        """Abre QMenu com checkboxes para cada opção do spec."""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: white; color: #142430;"
            " border: 1px solid #D1D5DB; border-radius: 6px;"
            " padding: 4px; }"
            "QMenu::item { padding: 4px 8px; }"
            "QMenu::item:selected { background-color: #F3F4F6; }"
        )

        for opcao in self._spec.opcoes:
            wa = QWidgetAction(menu)
            cb = QCheckBox(f"  {opcao}")
            cb.setChecked(opcao in self._selected)
            cb.setStyleSheet(
                "QCheckBox { color: #142430; padding: 4px 8px;"
                " background: transparent; }"
            )
            cb.toggled.connect(self._make_toggle_handler(opcao))
            wa.setDefaultWidget(cb)
            menu.addAction(wa)

        # Posicionar abaixo do botão "▾".
        menu.exec(self._open_btn.mapToGlobal(
            QPoint(0, self._open_btn.height()),
        ))

    def _make_toggle_handler(self, opcao: str) -> Any:
        """Closure que captura o nome da opção marcada/desmarcada."""
        def handler(checked: bool) -> None:
            if checked:
                self._selected.add(opcao)
            else:
                self._selected.discard(opcao)
            self._refresh_chips()
        return handler

    def _refresh_chips(self) -> None:
        """Re-renderiza os chips dos valores selecionados."""
        # Remove widgets antigos (preserva o stretch ao final).
        while self._chips_layout.count() > 1:
            item = self._chips_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()

        for opcao in self.values():
            # Round 3b-2: cor vem do override map (paleta brand). QSS aceita
            # rgba() em background-color, então usamos pal.bg direto sem
            # parse — diferente de delegates.py que pinta via QPainter.
            pal = resolve_chip_color(self._base_label, self._prop_key, opcao)
            chip = QLabel(opcao)
            chip.setStyleSheet(
                f"QLabel {{"
                f" background-color: {pal.bg};"
                f" color: {pal.fg};"
                f" border-radius: {_CHIP_RADIUS}px;"
                f" padding: {_CHIP_PADDING_V}px {_CHIP_PADDING_H}px;"
                f" font-size: 11px; }}"
            )
            self._chips_layout.insertWidget(
                self._chips_layout.count() - 1, chip,
            )
